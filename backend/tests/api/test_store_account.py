"""Every route of /api/v1/store/account."""

from typing import Any

from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from modellbahn.platform.mail import InMemoryMailer
from modellbahn.platform.outbox import outbox_table
from tests.api.helpers import (
    EMAIL,
    NEW_PASSWORD,
    PASSWORD,
    STORE,
    ClientFactory,
    assert_problem,
    cookie_attributes,
    register,
)
from tests.conftest import Deliver
from tests.support import token_from


async def event_types(engine: AsyncEngine) -> list[str]:
    async with engine.connect() as connection:
        rows = await connection.scalars(
            select(outbox_table.c.event_type).order_by(outbox_table.c.id)
        )
        return list(rows)


async def login(client: AsyncClient, password: str = PASSWORD, email: str = EMAIL) -> Response:
    return await client.post(f"{STORE}/session", json={"email": email, "password": password})


class TestRegistration:
    async def test_existing_address_gets_the_same_answer(
        self, client: AsyncClient, engine: AsyncEngine, deliver: Deliver, mailer: InMemoryMailer
    ) -> None:
        first = await register(client)
        second = await register(client, email="KUNDE@example.com", name="Mallory")
        assert first.status_code == second.status_code == 202
        assert first.json() == second.json() == {"status": "pending_verification"}
        assert set(first.headers) == set(second.headers)

        await deliver()
        verification, notice = mailer.sent
        assert verification.subject == "Bitte bestätige deine E-Mail-Adresse"
        assert notice.subject == "Für diese Adresse gibt es schon ein Konto"
        assert await event_types(engine) == [
            "identity.customer.registered",
            "identity.customer.registration_attempted_existing",
        ]

    async def test_validation_problems(self, client: AsyncClient) -> None:
        short = assert_problem(await register(client, password="kurz"), 422, "validation_failed")
        assert short["errors"] == [
            {"field": "password", "code": "too_short", "message": short["errors"][0]["message"]}
        ]
        same = assert_problem(await register(client, password=EMAIL), 422, "validation_failed")
        assert [(e["field"], e["code"]) for e in same["errors"]] == [("password", "equals_email")]

        response = await client.post(
            f"{STORE}/register",
            json={"email": "kein-mail", "password": PASSWORD, "display_name": "", "admin": True},
        )
        body = assert_problem(response, 422, "validation_failed")
        assert sorted((e["field"], e["code"]) for e in body["errors"]) == [
            ("admin", "unknown_field"),
            ("display_name", "too_short"),
            ("email", "invalid"),
        ]

    async def test_control_characters_in_the_name_are_rejected(self, client: AsyncClient) -> None:
        body = assert_problem(await register(client, name="Erika\x00"), 422, "validation_failed")
        assert [(e["field"], e["code"]) for e in body["errors"]] == [("display_name", "invalid")]


class TestVerification:
    async def test_verify_sets_the_session_cookie(
        self, client: AsyncClient, deliver: Deliver, mailer: InMemoryMailer
    ) -> None:
        await register(client)
        await deliver()
        response = await client.post(
            f"{STORE}/email-verification", json={"token": token_from(mailer.sent[-1])}
        )
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"id", "email", "display_name", "email_verified", "created_at"}
        assert body["email"] == EMAIL
        assert body["email_verified"] is True

        cookie = cookie_attributes(response, "mb_session")
        assert cookie["max-age"] == str(30 * 24 * 3600)
        assert cookie["path"] == "/"
        assert cookie["samesite"] == "lax"
        assert "httponly" in cookie
        assert "secure" in cookie
        assert len(cookie["value"]) == 43

        me = await client.get(f"{STORE}/me")
        assert me.json() == body

    async def test_invalid_token(self, client: AsyncClient) -> None:
        response = await client.post(f"{STORE}/email-verification", json={"token": "abc"})
        assert_problem(response, 400, "invalid_token")

    async def test_resend_answers_alike(
        self, client: AsyncClient, deliver: Deliver, mailer: InMemoryMailer
    ) -> None:
        await register(client)
        known = await client.post(f"{STORE}/email-verification/resend", json={"email": EMAIL})
        unknown = await client.post(
            f"{STORE}/email-verification/resend", json={"email": "niemand@example.com"}
        )
        assert known.status_code == unknown.status_code == 202
        assert known.json() == unknown.json() == {"status": "accepted"}
        await deliver()
        assert [mail.subject for mail in mailer.sent] == [
            "Bitte bestätige deine E-Mail-Adresse"
        ] * 2


class TestSession:
    async def test_login_logout(self, client: AsyncClient, customer: dict[str, Any]) -> None:
        await client.delete(f"{STORE}/session")
        assert_problem(await client.get(f"{STORE}/me"), 401, "not_authenticated")

        response = await login(client)
        assert response.status_code == 200
        assert response.json() == customer
        assert (await client.get(f"{STORE}/me")).status_code == 200

        logout = await client.delete(f"{STORE}/session")
        assert logout.status_code == 204
        assert cookie_attributes(logout, "mb_session")["max-age"] == "0"
        # Idempotent.
        assert (await client.delete(f"{STORE}/session")).status_code == 204

    async def test_wrong_password_and_unverified_account(self, client: AsyncClient) -> None:
        assert_problem(await login(client), 401, "invalid_credentials")
        await register(client)
        assert_problem(await login(client, "falsches Passwort"), 401, "invalid_credentials")
        assert_problem(await login(client), 403, "email_not_verified")

    async def test_locked_account_answers_like_wrong_credentials(
        self, client: AsyncClient, customer: dict[str, Any]
    ) -> None:
        for _ in range(5):
            assert_problem(await login(client, "falsches Passwort"), 401, "invalid_credentials")
        locked = assert_problem(await login(client), 401, "invalid_credentials")
        unknown = assert_problem(
            await login(client, email="niemand@example.com"), 401, "invalid_credentials"
        )
        assert locked == unknown

    async def test_stale_cookie_is_cleared(self, make_client: ClientFactory) -> None:
        async with make_client() as client:
            client.cookies.set("mb_session", "forged-or-expired")
            response = await client.get(f"{STORE}/me")
        assert_problem(response, 401, "not_authenticated")
        assert cookie_attributes(response, "mb_session")["max-age"] == "0"


class TestAccountChanges:
    async def test_rename(self, client: AsyncClient, customer: dict[str, Any]) -> None:
        response = await client.patch(f"{STORE}/me", json={"display_name": "  Erika  M. "})
        assert response.status_code == 200
        assert response.json()["display_name"] == "Erika M."
        response = await client.patch(f"{STORE}/me", json={"display_name": "x" * 81})
        assert_problem(response, 422, "validation_failed")

    async def test_change_password_ends_other_sessions(
        self,
        client: AsyncClient,
        customer: dict[str, Any],
        make_client: ClientFactory,
        engine: AsyncEngine,
    ) -> None:
        async with make_client() as other:
            assert (await login(other)).status_code == 200

            wrong = await client.post(
                f"{STORE}/password",
                json={"current_password": "falsches Passwort", "new_password": NEW_PASSWORD},
            )
            assert_problem(wrong, 400, "invalid_password")
            weak = await client.post(
                f"{STORE}/password", json={"current_password": PASSWORD, "new_password": EMAIL}
            )
            body = assert_problem(weak, 422, "validation_failed")
            assert body["errors"][0]["field"] == "new_password"

            response = await client.post(
                f"{STORE}/password",
                json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            )
            assert response.status_code == 204
            assert (await client.get(f"{STORE}/me")).status_code == 200
            assert_problem(await other.get(f"{STORE}/me"), 401, "not_authenticated")
        assert (await event_types(engine))[-1] == "identity.account.password_changed"
        assert (await login(client, NEW_PASSWORD)).status_code == 200

    async def test_password_reset(
        self,
        client: AsyncClient,
        customer: dict[str, Any],
        deliver: Deliver,
        mailer: InMemoryMailer,
    ) -> None:
        known = await client.post(f"{STORE}/password-reset", json={"email": EMAIL})
        unknown = await client.post(
            f"{STORE}/password-reset", json={"email": "niemand@example.com"}
        )
        assert known.status_code == unknown.status_code == 202
        assert known.json() == unknown.json()
        await deliver()
        mail = mailer.sent[-1]
        assert "/konto/passwort-zuruecksetzen?token=" in mail.text

        bad = await client.post(
            f"{STORE}/password-reset/confirm", json={"token": "abc", "new_password": NEW_PASSWORD}
        )
        assert_problem(bad, 400, "invalid_token")
        response = await client.post(
            f"{STORE}/password-reset/confirm",
            json={"token": token_from(mail), "new_password": NEW_PASSWORD},
        )
        assert response.status_code == 204
        # Every session ended, including this one.
        assert_problem(await client.get(f"{STORE}/me"), 401, "not_authenticated")
        assert_problem(await login(client), 401, "invalid_credentials")
        assert (await login(client, NEW_PASSWORD)).status_code == 200

    async def test_delete_account(
        self, client: AsyncClient, customer: dict[str, Any], engine: AsyncEngine
    ) -> None:
        wrong = await client.post(f"{STORE}/me/delete", json={"password": "falsches Passwort"})
        assert_problem(wrong, 400, "invalid_password")

        response = await client.post(f"{STORE}/me/delete", json={"password": PASSWORD})
        assert response.status_code == 204
        assert cookie_attributes(response, "mb_session")["max-age"] == "0"
        assert_problem(await client.get(f"{STORE}/me"), 401, "not_authenticated")
        assert_problem(await login(client), 401, "invalid_credentials")
        assert (await event_types(engine))[-1] == "identity.account.deleted"

    async def test_routes_need_a_customer_session(self, client: AsyncClient) -> None:
        for method, path, body in [
            ("GET", "/me", None),
            ("PATCH", "/me", {"display_name": "X"}),
            ("POST", "/password", {"current_password": PASSWORD, "new_password": NEW_PASSWORD}),
            ("POST", "/me/delete", {"password": PASSWORD}),
        ]:
            response = await client.request(method, f"{STORE}{path}", json=body)
            assert_problem(response, 401, "not_authenticated")
