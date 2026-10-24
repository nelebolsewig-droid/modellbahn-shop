"""Staff login for the admin area, and the separation of shop and admin sessions."""

from typing import Any

from httpx import AsyncClient

from modellbahn.modules.identity.application.services import IdentityService
from modellbahn.modules.identity.domain.model import StaffRole
from tests.api.helpers import (
    ADMIN,
    NEW_PASSWORD,
    PASSWORD,
    STAFF_EMAIL,
    STORE,
    ClientFactory,
    assert_problem,
    cookie_attributes,
)


async def test_staff_login_sets_a_strict_admin_cookie(
    make_client: ClientFactory, identity: IdentityService
) -> None:
    staff = await identity.create_staff(
        email=STAFF_EMAIL, display_name="Chefin", role=StaffRole.OWNER, password=PASSWORD
    )
    async with make_client() as client:
        wrong = await client.post(
            f"{ADMIN}/session", json={"email": STAFF_EMAIL, "password": "falsches Passwort"}
        )
        assert_problem(wrong, 401, "invalid_credentials")

        response = await client.post(
            f"{ADMIN}/session", json={"email": STAFF_EMAIL, "password": PASSWORD}
        )
        assert response.status_code == 200
        assert response.json() == {
            "id": str(staff.id),
            "email": STAFF_EMAIL,
            "display_name": "Chefin",
            "role": "owner",
        }
        cookie = cookie_attributes(response, "mb_admin")
        assert cookie["samesite"] == "strict"
        assert cookie["max-age"] == str(12 * 3600)
        assert "httponly" in cookie
        assert "secure" in cookie

        assert (await client.get(f"{ADMIN}/me")).json()["role"] == "owner"


async def test_staff_change_password_and_logout(staff_client: AsyncClient) -> None:
    wrong = await staff_client.post(
        f"{ADMIN}/password",
        json={"current_password": "falsches Passwort", "new_password": NEW_PASSWORD},
    )
    assert_problem(wrong, 400, "invalid_password")
    response = await staff_client.post(
        f"{ADMIN}/password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD}
    )
    assert response.status_code == 204
    assert (await staff_client.get(f"{ADMIN}/me")).status_code == 200

    logout = await staff_client.delete(f"{ADMIN}/session")
    assert logout.status_code == 204
    assert cookie_attributes(logout, "mb_admin")["max-age"] == "0"
    assert_problem(await staff_client.get(f"{ADMIN}/me"), 401, "not_authenticated")
    assert (await staff_client.delete(f"{ADMIN}/session")).status_code == 204


async def test_customers_cannot_log_in_to_the_admin_area(
    client: AsyncClient, customer: dict[str, Any]
) -> None:
    response = await client.post(
        f"{ADMIN}/session", json={"email": customer["email"], "password": PASSWORD}
    )
    assert_problem(response, 401, "invalid_credentials")


async def test_a_staff_session_never_opens_the_shop_and_vice_versa(
    staff_client: AsyncClient,
    client: AsyncClient,
    customer: dict[str, Any],
    make_client: ClientFactory,
) -> None:
    staff_token = staff_client.cookies["mb_admin"]
    customer_token = client.cookies["mb_session"]
    async with make_client() as mixed:
        # The right token under the wrong cookie name, in both directions.
        mixed.cookies.set("mb_session", staff_token)
        mixed.cookies.set("mb_admin", customer_token)
        assert_problem(await mixed.get(f"{STORE}/me"), 401, "not_authenticated")
        assert_problem(await mixed.get(f"{ADMIN}/me"), 401, "not_authenticated")
        assert_problem(await mixed.get("/api/v1/admin/events"), 401, "not_authenticated")

    # Each cookie keeps working in its own area.
    assert (await client.get(f"{STORE}/me")).status_code == 200
    assert (await staff_client.get(f"{ADMIN}/me")).status_code == 200
    assert_problem(await staff_client.get(f"{STORE}/me"), 401, "not_authenticated")
    assert_problem(await client.get(f"{ADMIN}/me"), 401, "not_authenticated")
