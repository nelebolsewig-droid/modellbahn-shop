"""The site API: fairs, their calendar, the fair news with double opt-in, the imprint."""

from typing import Any, Final

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from modellbahn.main import create_app
from modellbahn.platform.config import Settings
from modellbahn.platform.mail import InMemoryMailer
from tests.api.helpers import SHOP, assert_problem
from tests.conftest import PUBLIC_BASE_URL, Deliver
from tests.support import CSRF_HEADERS, mails_to, token_from

FAIRS: Final = "/api/v1/admin/fairs"
DRESDEN: Final = {
    "name": "Kleinserienmesse Dresden",
    "venue": "JohannStadthalle",
    "street": "Holbeinstraße 68",
    "postal_code": "01307",
    "city": "Dresden",
    "starts_on": "2099-11-07",
    "ends_on": "2099-11-07",
    "published": True,
}


async def create_fair(staff: AsyncClient, **changes: Any) -> dict[str, Any]:
    response = await staff.post(FAIRS, json={**DRESDEN, **changes})
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


class TestFairs:
    async def test_staff_keep_fairs_and_the_shop_shows_the_published(
        self, staff_client: AsyncClient, client: AsyncClient
    ) -> None:
        fair = await create_fair(staff_client)
        await create_fair(staff_client, name="Entwurf", published=False)
        assert fair["when"] == "7. November 2099"

        shown = await client.get(f"{SHOP}/fairs")
        assert shown.status_code == 200
        assert shown.headers["cache-control"] == "public, max-age=60"
        assert [item["name"] for item in shown.json()["upcoming"]] == ["Kleinserienmesse Dresden"]
        assert "published" not in shown.json()["upcoming"][0]

        changed = await staff_client.put(
            f"{FAIRS}/{fair['id']}", json={**DRESDEN, "booth": "Stand 12", "published": False}
        )
        assert changed.json()["booth"] == "Stand 12"
        assert (await client.get(f"{SHOP}/fairs")).json()["upcoming"] == []
        assert (await staff_client.delete(f"{FAIRS}/{fair['id']}")).status_code == 204
        assert len((await staff_client.get(FAIRS)).json()["items"]) == 1

    async def test_checks_the_details(self, staff_client: AsyncClient) -> None:
        response = await staff_client.post(FAIRS, json={**DRESDEN, "ends_on": "2099-11-06"})
        body = assert_problem(response, 422, "validation_failed")
        assert body["errors"][0]["field"] == "ends_on"

    async def test_packers_keep_out(self, packer_client: AsyncClient) -> None:
        assert_problem(await packer_client.get(FAIRS), 403, "insufficient_role")

    async def test_calendar_for_one_fair_and_for_all(
        self, staff_client: AsyncClient, client: AsyncClient
    ) -> None:
        fair = await create_fair(staff_client)
        single = await client.get(f"{SHOP}/fairs/{fair['id']}/calendar.ics")
        assert single.status_code == 200
        assert single.headers["content-type"] == "text/calendar; charset=utf-8"
        assert "attachment" in single.headers["content-disposition"]
        assert "SUMMARY:Modellbahn-Shop auf der Messe: Kleinserienmesse Dresden" in single.text
        feed = await client.get(f"{SHOP}/fairs/calendar.ics")
        assert feed.text.count("BEGIN:VEVENT") == 1
        draft = await create_fair(staff_client, published=False)
        missing = await client.get(f"{SHOP}/fairs/{draft['id']}/calendar.ics")
        assert_problem(missing, 404, "fair_not_found")


class TestFairNews:
    async def test_sign_up_confirm_and_announce(
        self,
        client: AsyncClient,
        staff_client: AsyncClient,
        deliver: Deliver,
        mailer: InMemoryMailer,
    ) -> None:
        refused = await client.post(
            f"{SHOP}/fair-news/subscriptions", json={"email": "erika@example.de", "consent": False}
        )
        assert assert_problem(refused, 422, "validation_failed")["errors"][0]["field"] == "consent"
        asked = await client.post(
            f"{SHOP}/fair-news/subscriptions", json={"email": "erika@example.de", "consent": True}
        )
        assert asked.status_code == 202
        await deliver()
        token = token_from(mails_to(mailer, "erika@example.de")[-1])
        wrong = await client.post(f"{SHOP}/fair-news/confirmations", json={"token": "x"})
        assert_problem(wrong, 400, "fair_news_token_invalid")
        confirmed = await client.post(f"{SHOP}/fair-news/confirmations", json={"token": token})
        assert confirmed.status_code == 204
        assert (await staff_client.get("/api/v1/admin/fair-news")).json() == {
            "confirmed": 1,
            "pending": 0,
        }

        fair = await create_fair(staff_client)
        announced = await staff_client.post(f"{FAIRS}/{fair['id']}/announcement")
        assert announced.status_code == 202
        assert announced.json()["recipients"] == 1
        assert announced.json()["fair"]["announced_at"] is not None
        again = await staff_client.post(f"{FAIRS}/{fair['id']}/announcement")
        assert_problem(again, 409, "fair_already_announced")
        await deliver()
        assert mails_to(mailer, "erika@example.de")[-1].subject.startswith("Wir stellen aus")

    async def test_leaving_is_always_fine(self, client: AsyncClient) -> None:
        left = await client.post(f"{SHOP}/fair-news/unsubscriptions", json={"token": "alt"})
        assert left.status_code == 204

    async def test_the_form_is_limited_per_address(self, settings: Settings) -> None:
        app: FastAPI = create_app(settings.model_copy(update={"fair_news_rate_limit": 2}))
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url=PUBLIC_BASE_URL, headers=CSRF_HEADERS
        ) as client:
            for _ in range(2):
                await client.post(f"{SHOP}/fair-news/unsubscriptions", json={"token": "alt"})
            limited = await client.post(f"{SHOP}/fair-news/unsubscriptions", json={"token": "alt"})
        assert_problem(limited, 429, "too_many_requests")


class TestImprint:
    async def test_names_the_provider_from_the_settings(self, client: AsyncClient) -> None:
        response = await client.get(f"{SHOP}/imprint")
        assert response.status_code == 200
        assert response.json() == {
            "shop_name": "Modellbahn-Shop",
            "company": "adp-Modelle",
            "owner": "Johann-Leon Diesterhaupt",
            "street": "Glambecker Straße 2",
            "postal_code": "17235",
            "city": "Neustrelitz",
            "country": "Deutschland",
            "phone": "0160 91515272",
            "email": "info@adp-modelle.de",
            "vat_id": "",
            "complete": True,
        }
