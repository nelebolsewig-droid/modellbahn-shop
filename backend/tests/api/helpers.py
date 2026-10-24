"""Constants and helpers of the API tests."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any, Final

from httpx import AsyncClient, Response

EMAIL: Final = "kunde@example.com"
PASSWORD: Final = "Gleis 7 und Weiche 3"
NEW_PASSWORD: Final = "Neues sicheres Passwort"
STAFF_EMAIL: Final = "chefin@example.com"
STORE: Final = "/api/v1/store/account"
ADMIN: Final = "/api/v1/admin/auth"

type ClientFactory = Callable[..., AbstractAsyncContextManager[AsyncClient]]


async def register(
    client: AsyncClient, email: str = EMAIL, password: str = PASSWORD, name: str = "Erika"
) -> Response:
    return await client.post(
        f"{STORE}/register", json={"email": email, "password": password, "display_name": name}
    )


def assert_problem(response: Response, status: int, code: str) -> dict[str, Any]:
    """Check the RFC 9457 shape and return the body."""
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/problem+json"
    body: dict[str, Any] = response.json()
    assert body["status"] == status
    assert body["code"] == code
    assert body["type"] == f"/problems/{code.replace('_', '-')}"
    assert isinstance(body["title"], str)
    assert isinstance(body["detail"], str)
    return body


def cookie_attributes(response: Response, name: str) -> dict[str, str]:
    """The attributes of the ``Set-Cookie`` header for ``name`` (lower-case keys)."""
    for header in response.headers.get_list("set-cookie"):
        first, *attributes = (part.strip() for part in header.split(";"))
        cookie_name, _, value = first.partition("=")
        if cookie_name == name:
            parsed = {"value": value}
            for attribute in attributes:
                key, _, attribute_value = attribute.partition("=")
                parsed[key.lower()] = attribute_value
            return parsed
    raise AssertionError(f"no Set-Cookie for {name}")
