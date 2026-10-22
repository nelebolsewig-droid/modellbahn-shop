"""Settings, clock, security primitives and error mapping."""

import logging
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from modellbahn.platform.clock import FixedClock, SystemClock
from modellbahn.platform.config import Environment, Settings
from modellbahn.platform.errors import _field_error
from modellbahn.platform.logging import configure_logging
from modellbahn.platform.security import Argon2PasswordHasher, generate_token, hash_token


class TestSettings:
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
            Settings(environment=Environment.PRODUCTION, cookie_secure=False)
        assert Settings(environment=Environment.PRODUCTION).is_production

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
