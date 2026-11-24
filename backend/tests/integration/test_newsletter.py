"""The newsletter against PostgreSQL, with the real outbox dispatcher."""

import re
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from modellbahn.modules.catalog.application.services import CatalogService
from modellbahn.modules.identity.application.services import IdentityService
from modellbahn.modules.media.application.services import MediaService
from modellbahn.modules.newsletter.application.issues import IssueService
from modellbahn.modules.newsletter.application.subscriptions import (
    ReaderStatus,
    SubscriptionService,
)
from modellbahn.modules.newsletter.domain.errors import NewsletterTokenInvalidError
from modellbahn.modules.sales.application.cart import CartService
from modellbahn.modules.sales.application.checkout import Buyer, CheckoutService
from modellbahn.platform.clock import FixedClock
from modellbahn.platform.mail import InMemoryMailer, OutgoingMail
from tests.conftest import Deliver
from tests.media_support import InMemoryMediaStorage
from tests.sales_support import filled_cart, place, shop_product, variant_id
from tests.support import mails_to, token_from

pytestmark = pytest.mark.usefixtures("clean_database")

PASSWORD = "ein sicheres Passwort"
ERIKA = "erika@example.de"
# The 1st of December 2026, 10:00 in Berlin: an issue day, during the day.
ISSUE_MORNING = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)


async def registered(
    identity: IdentityService,
    deliver: Deliver,
    email: str = ERIKA,
    *,
    newsletter: bool = False,
) -> None:
    await identity.register_customer(
        email=email, password=PASSWORD, display_name="Erika", newsletter=newsletter
    )
    await deliver()


async def verify(
    identity: IdentityService, deliver: Deliver, mailer: InMemoryMailer, email: str = ERIKA
) -> UUID:
    started = await identity.verify_email(
        token=token_from(mails_to(mailer, email)[0]), password=PASSWORD, user_agent=None
    )
    await deliver()
    return started.account.id


def newsletter_mails(mailer: InMemoryMailer, email: str = ERIKA) -> list[OutgoingMail]:
    return [m for m in mails_to(mailer, email) if "Newsletter" in m.subject]


def unsubscribe_token(mail: OutgoingMail) -> str:
    match = re.search(r"/newsletter/abmelden\?token=([A-Za-z0-9_-]+)", mail.text)
    assert match is not None, "no way out in the mail"
    return match.group(1)


async def reader(
    identity: IdentityService,
    deliver: Deliver,
    mailer: InMemoryMailer,
    newsletter: SubscriptionService,
    email: str = ERIKA,
) -> UUID:
    await registered(identity, deliver, email)
    account = await verify(identity, deliver, mailer, email)
    await newsletter.subscribe(account)
    await deliver()
    await newsletter.confirm(token_from(newsletter_mails(mailer, email)[-1]))
    return account


class TestConsent:
    async def test_ticked_at_registration_the_link_follows_the_verification(
        self,
        identity: IdentityService,
        newsletter: SubscriptionService,
        deliver: Deliver,
        mailer: InMemoryMailer,
    ) -> None:
        await registered(identity, deliver, newsletter=True)
        # Only the verification so far: an unverified address gets no newsletter mail.
        assert newsletter_mails(mailer) == []
        account = await verify(identity, deliver, mailer)
        assert await newsletter.status(account) is ReaderStatus.PENDING
        [confirmation] = newsletter_mails(mailer)
        assert "bestätige" in confirmation.subject
        assert "/newsletter/bestaetigen?token=" in confirmation.text

        await newsletter.confirm(token_from(confirmation))
        assert await newsletter.status(account) is ReaderStatus.CONFIRMED
        with pytest.raises(NewsletterTokenInvalidError):
            await newsletter.confirm(token_from(confirmation))

    async def test_not_ticked_means_no_newsletter(
        self,
        identity: IdentityService,
        newsletter: SubscriptionService,
        deliver: Deliver,
        mailer: InMemoryMailer,
    ) -> None:
        await registered(identity, deliver)
        account = await verify(identity, deliver, mailer)
        assert await newsletter.status(account) is ReaderStatus.NONE
        assert newsletter_mails(mailer) == []

    async def test_in_the_account_and_out_again(
        self,
        identity: IdentityService,
        newsletter: SubscriptionService,
        deliver: Deliver,
        mailer: InMemoryMailer,
    ) -> None:
        account = await reader(identity, deliver, mailer, newsletter)
        assert await newsletter.subscribe(account) is ReaderStatus.CONFIRMED
        await newsletter.unsubscribe_account(account)
        assert await newsletter.status(account) is ReaderStatus.NONE
        assert (await newsletter.counts()).confirmed == 0

    async def test_unconfirmed_requests_are_forgotten(
        self,
        identity: IdentityService,
        newsletter: SubscriptionService,
        deliver: Deliver,
        mailer: InMemoryMailer,
        clock: FixedClock,
    ) -> None:
        await registered(identity, deliver)
        account = await verify(identity, deliver, mailer)
        await newsletter.subscribe(account)
        await deliver()
        clock.advance(timedelta(days=15))
        assert await newsletter.purge_pending() == 1
        assert await newsletter.status(account) is ReaderStatus.NONE

    async def test_a_deleted_account_leaves_the_newsletter(
        self,
        identity: IdentityService,
        newsletter: SubscriptionService,
        deliver: Deliver,
        mailer: InMemoryMailer,
    ) -> None:
        account = await reader(identity, deliver, mailer, newsletter)
        await identity.delete_account(account_id=account, password=PASSWORD)
        await deliver()
        assert (await newsletter.counts()).confirmed == 0


class TestIssues:
    async def test_new_models_and_what_suits_each_reader(
        self,
        identity: IdentityService,
        newsletter: SubscriptionService,
        issues: IssueService,
        catalog: CatalogService,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        carts: CartService,
        checkout: CheckoutService,
        deliver: Deliver,
        mailer: InMemoryMailer,
        clock: FixedClock,
    ) -> None:
        bought = await shop_product(catalog, media, media_storage, deliver, name="Wartburg 353")
        older = await shop_product(catalog, media, media_storage, deliver, name="Trabant 601")
        # Same category as the Wartburg: that suits Erika.
        await catalog.change_product(
            older.product.id,
            expected_version=None,
            primary_category_id=bought.product.primary_category_id,
        )
        erika = await reader(identity, deliver, mailer, newsletter)
        max_ = await reader(identity, deliver, mailer, newsletter, "max@example.de")
        cart = await filled_cart(carts, (variant_id(bought, "H0", "painted"), 1))
        order = (
            await place(checkout, carts, cart, buyer=Buyer(account_id=erika, email=ERIKA))
        ).details.order
        await checkout.pay(
            public_token=order.public_token, method="succeeds", idempotency_key=uuid4()
        )
        await deliver()

        clock.set(ISSUE_MORNING)
        await shop_product(catalog, media, media_storage, deliver, name="IFA W50")
        assert await issues.release_if_due()
        assert not await issues.release_if_due(), "one issue a day"
        await deliver()

        [to_erika] = [m for m in mails_to(mailer, ERIKA) if m.subject.startswith("Neu bei")]
        assert "IFA W50" in to_erika.subject
        assert "Passt zu deiner Sammlung" in to_erika.html
        assert "Trabant 601" in to_erika.text
        assert "Wartburg 353" not in to_erika.text, "she has it already"
        assert to_erika.unsubscribe_url is not None
        assert "/webhooks/newsletter/unsubscribe" in to_erika.unsubscribe_url
        assert "<img" in to_erika.html

        [to_max] = [m for m in mails_to(mailer, "max@example.de") if m.subject.startswith("Neu")]
        assert "Passt zu deiner Sammlung" not in to_max.html, "Max bought nothing yet"

        overview = await issues.overview()
        assert [(p.number, p.sent) for p in overview.recent] == [(1, 2)]
        assert overview.waiting == []
        assert max_ != erika

        await newsletter.unsubscribe(unsubscribe_token(to_erika))
        assert await newsletter.status(erika) is ReaderStatus.NONE

    async def test_nothing_new_means_no_issue(
        self,
        identity: IdentityService,
        newsletter: SubscriptionService,
        issues: IssueService,
        deliver: Deliver,
        mailer: InMemoryMailer,
        clock: FixedClock,
    ) -> None:
        await reader(identity, deliver, mailer, newsletter)
        clock.set(ISSUE_MORNING)
        assert not await issues.release_if_due()

    async def test_only_on_issue_days(
        self,
        catalog: CatalogService,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        issues: IssueService,
        deliver: Deliver,
        clock: FixedClock,
    ) -> None:
        clock.set(ISSUE_MORNING + timedelta(days=1))
        await shop_product(catalog, media, media_storage, deliver, name="IFA W50")
        assert not await issues.release_if_due()
        overview = await issues.overview()
        assert overview.waiting == ["IFA W50"]
        assert overview.next_issue is not None
        assert overview.next_issue.day == 15

    async def test_the_preview(
        self,
        catalog: CatalogService,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        issues: IssueService,
        deliver: Deliver,
    ) -> None:
        await shop_product(catalog, media, media_storage, deliver, name="IFA W50")
        mail, _ = await issues.preview()
        assert "IFA W50" in mail.subject
        assert "Max Mustermann" in mail.text
