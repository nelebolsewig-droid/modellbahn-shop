"""The newsletter API: the switch in the account, the mail links, the Stellwerk page."""

from typing import Any, Final

from httpx import AsyncClient

from modellbahn.platform.mail import InMemoryMailer
from tests.api.helpers import EMAIL, SHOP, ClientFactory, assert_problem
from tests.conftest import Deliver
from tests.support import mails_to, token_from

NEWSLETTER: Final = f"{SHOP}/account/newsletter"


def newsletter_mail(mailer: InMemoryMailer) -> Any:
    return [m for m in mails_to(mailer, EMAIL) if "Newsletter" in m.subject][-1]


class TestShop:
    async def test_switch_on_confirm_and_leave(
        self,
        client: AsyncClient,
        customer: dict[str, Any],
        deliver: Deliver,
        mailer: InMemoryMailer,
    ) -> None:
        assert (await client.get(NEWSLETTER)).json() == {"status": "none"}
        response = await client.put(NEWSLETTER, json={"subscribed": True})
        assert response.json() == {"status": "pending"}
        await deliver()

        token = token_from(newsletter_mail(mailer))
        bad = await client.post(f"{SHOP}/newsletter/confirmations", json={"token": "falsch"})
        assert_problem(bad, 400, "newsletter_token_invalid")
        confirmed = await client.post(f"{SHOP}/newsletter/confirmations", json={"token": token})
        assert confirmed.status_code == 204
        assert (await client.get(NEWSLETTER)).json() == {"status": "confirmed"}

        left = await client.put(NEWSLETTER, json={"subscribed": False})
        assert left.json() == {"status": "none"}

    async def test_the_links_need_no_login(
        self, client: AsyncClient, make_client: ClientFactory
    ) -> None:
        assert (await client.get(NEWSLETTER)).status_code == 401
        gone = await client.post(f"{SHOP}/newsletter/unsubscriptions", json={"token": "x"})
        assert gone.status_code == 204
        # The mail program's button: no CSRF header, a form body.
        async with make_client(csrf=False) as mail_program:
            one_click = await mail_program.post(
                "/api/v1/webhooks/newsletter/unsubscribe?token=x",
                content="List-Unsubscribe=One-Click",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        assert one_click.status_code == 204


class TestStellwerk:
    async def test_overview_and_preview(self, staff_client: AsyncClient) -> None:
        overview = await staff_client.get("/api/v1/admin/newsletter")
        assert overview.status_code == 200, overview.text
        body = overview.json()
        assert (body["confirmed"], body["pending"], body["issue_days"]) == (0, 0, [1, 15])
        assert body["recent"] == []
        preview = await staff_client.get("/api/v1/admin/newsletter/preview")
        assert preview.status_code == 200
        assert "Max Mustermann" in preview.json()["html"]

    async def test_customers_do_not_get_in(
        self, client: AsyncClient, customer: dict[str, Any]
    ) -> None:
        assert (await client.get("/api/v1/admin/newsletter")).status_code == 401
