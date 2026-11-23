"""Settings, clock, security primitives and error mapping."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from modellbahn.platform.clock import FixedClock, SystemClock
from modellbahn.platform.config import Environment, PaymentProvider, Settings
from modellbahn.platform.errors import _field_error
from modellbahn.platform.logging import configure_logging
from modellbahn.platform.security import Argon2PasswordHasher, generate_token, hash_token
from modellbahn.platform.whatsapp import CallMeBotWhatsApp, WhatsAppRecipient, parse_recipients

OWN_KEY = "GK0123456789abcdef01234567"


# The provider details production insists on (§ 5 DDG).
IMPRINT: Final[dict[str, Any]] = {
    "imprint_company": "Gleiswerk",
    "imprint_owner": "Erika Mustermann",
    "imprint_street": "Bahnhofstraße 1",
    "imprint_postal_code": "38707",
    "imprint_city": "Altenau",
    "imprint_email": "info@gleiswerk.example",
}


class TestSettings:
    def test_morning_mail_goes_to_the_shop_and_the_extra_addresses(self) -> None:
        settings = Settings(
            imprint_email="info@example.com",
            digest_emails=" chef@example.com, ,INFO@example.com,werkstatt@example.com ",
        )
        assert settings.digest_recipients == (
            "info@example.com",
            "chef@example.com",
            "werkstatt@example.com",
        )
        assert Settings(imprint_email="").digest_recipients == ()

    def test_reads_prefixed_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MB_PUBLIC_BASE_URL", "https://shop.example/")
        monkeypatch.setenv("MB_LOG_LEVEL", "debug")
        monkeypatch.setenv("MB_SMTP_FROM", "Gleiswerk <shop@gleiswerk.example>")
        settings = Settings()
        assert settings.public_base_url == "https://shop.example"
        assert settings.log_level == "DEBUG"
        assert settings.shop_name == "Gleiswerk"
        assert settings.cookie_secure is True

    def test_shop_name_falls_back_to_default(self) -> None:
        assert Settings(smtp_from="noreply@example.com").shop_name == "Modellbahn-Shop"

    def test_production_refuses_insecure_cookies(self) -> None:
        with pytest.raises(ValidationError, match="MB_COOKIE_SECURE"):
            Settings(
                environment=Environment.PRODUCTION,
                cookie_secure=False,
                s3_access_key_id=OWN_KEY,
                **IMPRINT,
            )
        production = Settings(
            environment=Environment.PRODUCTION,
            s3_access_key_id=OWN_KEY,
            payment_provider=PaymentProvider.OFF,
            **IMPRINT,
        )
        assert production.is_production

    def test_production_refuses_the_test_payment(self) -> None:
        with pytest.raises(ValidationError, match="MB_PAYMENT_PROVIDER=mock"):
            Settings(environment=Environment.PRODUCTION, s3_access_key_id=OWN_KEY, **IMPRINT)

    def test_sumup_needs_its_key_and_merchant_code(self) -> None:
        with pytest.raises(ValidationError, match="MB_SUMUP_API_KEY, MB_SUMUP_MERCHANT_CODE"):
            Settings(payment_provider=PaymentProvider.SUMUP)
        with pytest.raises(ValidationError, match="MB_SUMUP_MERCHANT_CODE"):
            Settings(payment_provider=PaymentProvider.SUMUP, sumup_api_key=SecretStr("sup_sk_x"))
        sumup = Settings(
            environment=Environment.PRODUCTION,
            s3_access_key_id=OWN_KEY,
            payment_provider=PaymentProvider.SUMUP,
            sumup_api_key=SecretStr("sup_sk_x"),
            sumup_merchant_code="MC123",
            **IMPRINT,
        )
        assert sumup.payment_provider is PaymentProvider.SUMUP
        assert "sup_sk_x" not in repr(sumup)

    def test_production_needs_the_imprint(self) -> None:
        with pytest.raises(ValidationError, match="MB_IMPRINT_"):
            Settings(environment=Environment.PRODUCTION, s3_access_key_id=OWN_KEY)

    def test_vat_id_is_checked_and_tidied(self) -> None:
        assert Settings(imprint_vat_id="de 123 456 789").imprint.vat_id == "DE123456789"
        with pytest.raises(ValidationError, match="nine digits"):
            Settings(imprint_vat_id="DE12345")

    def test_production_refuses_the_development_storage_key(self) -> None:
        with pytest.raises(ValidationError, match="development storage key"):
            Settings(environment=Environment.PRODUCTION)

    def test_normalises_storage_urls(self) -> None:
        settings = Settings(
            s3_endpoint_url="http://storage:3900/",
            s3_public_endpoint_url="https://shop.example/",
            media_public_base_url="https://cdn.example/medien/",
        )
        assert settings.s3_endpoint_url == "http://storage:3900"
        assert settings.s3_public_endpoint_url == "https://shop.example"
        assert settings.media_public_base_url == "https://cdn.example/medien"

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("database_url", "postgresql://user@localhost/db"),
            ("smtp_from", "Shop without address"),
            ("public_base_url", "not a url"),
        ],
    )
    def test_rejects_invalid_values(self, field: str, value: str) -> None:
        with pytest.raises(ValidationError):
            Settings.model_validate({field: value})


class TestClock:
    def test_system_clock_is_utc(self) -> None:
        assert SystemClock().now().tzinfo is UTC

    def test_fixed_clock(self) -> None:
        clock = FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
        clock.advance(timedelta(minutes=5))
        assert clock.now() == datetime(2026, 1, 1, 0, 5, tzinfo=UTC)
        clock.set(datetime(2027, 1, 1, tzinfo=UTC))
        assert clock.now().year == 2027
        with pytest.raises(ValueError, match="timezone-aware"):
            FixedClock(datetime(2026, 1, 1))  # noqa: DTZ001


class TestTokens:
    def test_tokens_are_random_and_url_safe(self) -> None:
        tokens = {generate_token() for _ in range(100)}
        assert len(tokens) == 100
        assert all(len(token) == 43 and token.isascii() for token in tokens)

    def test_hash_is_sha256_hex(self) -> None:
        digest = hash_token("abc")
        assert digest == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


class TestArgon2:
    async def test_hash_verify_and_rehash(self) -> None:
        fast = Argon2PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
        stronger = Argon2PasswordHasher(time_cost=2, memory_cost=16, parallelism=1)
        password_hash = await fast.hash("geheimes Passwort")
        assert password_hash.startswith("$argon2id$")
        assert await fast.verify(password_hash, "geheimes Passwort")
        assert not await fast.verify(password_hash, "falsches Passwort")
        assert not await fast.verify("!unusable", "geheimes Passwort")
        assert not fast.needs_rehash(password_hash)
        assert stronger.needs_rehash(password_hash)
        assert not stronger.needs_rehash("!unusable")
        await fast.dummy_verify("irgendwas")


class TestFieldErrors:
    @pytest.mark.parametrize(
        ("error", "field", "code"),
        [
            ({"type": "missing", "loc": ("body", "email")}, "email", "required"),
            ({"type": "string_too_short", "loc": ("body", "password")}, "password", "too_short"),
            ({"type": "json_invalid", "loc": ("body", 12)}, "body", "invalid_json"),
            ({"type": "int_parsing", "loc": ("query", "page")}, "page", "invalid_type"),
            ({"type": "dict_type", "loc": ("body",)}, "body", "invalid_type"),
            ({"type": "value_error", "loc": ("body", "a", 0, "b")}, "a.0.b", "invalid"),
            ({"type": "missing", "loc": ()}, "", "required"),
        ],
    )
    def test_maps_pydantic_errors(self, error: dict[str, object], field: str, code: str) -> None:
        mapped = _field_error({**error, "msg": "Something"})
        assert (mapped.field, mapped.code, mapped.message) == (field, code, "Something")


def test_logging_routes_uvicorn_through_one_handler() -> None:
    configure_logging(environment=Environment.PRODUCTION, level="INFO")
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert root.level == logging.INFO
    assert logging.getLogger("uvicorn.error").propagate
    # The request middleware writes the access log; uvicorn's would duplicate it.
    assert not logging.getLogger("uvicorn.access").propagate
    configure_logging(environment=Environment.TEST, level="WARNING")


class TestWhatsApp:
    def test_recipients_from_the_setting(self) -> None:
        assert parse_recipients(" 0170 / 123-456:abc , +49160 99:def,nur-nummer, ") == (
            WhatsAppRecipient(phone="0170123456", api_key="abc"),
            WhatsAppRecipient(phone="+4916099", api_key="def"),
        )
        assert parse_recipients("0049170:k")[0].phone == "+49170"

    async def test_every_phone_gets_the_note_and_failures_do_not_raise(self) -> None:
        seen: list[httpx.URL] = []

        def handle(request: httpx.Request) -> httpx.Response:
            seen.append(request.url)
            return httpx.Response(500 if request.url.params["phone"] == "+492" else 200)

        bot = CallMeBotWhatsApp(
            [WhatsAppRecipient("+492", "x"), WhatsAppRecipient("+491", "y")],
            transport=httpx.MockTransport(handle),
        )
        await bot.send("Heute dran: 1 Paket packen")
        assert [u.params["phone"] for u in seen] == ["+492", "+491"]
        assert seen[1].params["text"] == "Heute dran: 1 Paket packen"
        assert seen[1].params["apikey"] == "y"
