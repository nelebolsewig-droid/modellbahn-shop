"""The identity mail handlers: content, idempotency and what they leave in the database."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from modellbahn.modules.identity.application.handlers import IdentityMailHandlers
from modellbahn.modules.identity.application.services import IdentityService, UnitOfWorkFactory
from modellbahn.modules.identity.domain.events import (
    CustomerRegistered,
    PasswordChanged,
    RegistrationAttemptedForExistingAccount,
)
from modellbahn.modules.identity.domain.model import Account, AccountKind, StaffRole
from modellbahn.modules.identity.infrastructure.tables import account_tokens
from modellbahn.platform.clock import FixedClock
from modellbahn.platform.mail import InMemoryMailer, OutgoingMail
from modellbahn.platform.security import hash_token
from tests.conftest import PUBLIC_BASE_URL, SHOP_NAME
from tests.support import token_from

EMAIL = "kunde@example.com"
PASSWORD = "Gleis 7 und Weiche 3"


class FailingMailer:
    async def send(self, mail: OutgoingMail) -> None:
        raise ConnectionRefusedError("SMTP server down")


async def token_count(engine: AsyncEngine) -> int:
    async with engine.connect() as connection:
        count = await connection.scalar(select(func.count()).select_from(account_tokens))
    return int(count or 0)


async def register(identity: IdentityService, uow_factory: UnitOfWorkFactory) -> Account:
    await identity.register_customer(email=EMAIL, password=PASSWORD, display_name="Erika")
    async with uow_factory() as uow:
        account = await uow.accounts.get_by_email(AccountKind.CUSTOMER, EMAIL)
    assert account is not None
    return account


def registered_event(account: Account, clock: FixedClock) -> CustomerRegistered:
    return CustomerRegistered(
        aggregate_id=account.id, occurred_at=clock.now(), display_name=account.display_name
    )


async def test_verification_mail(
    identity: IdentityService,
    uow_factory: UnitOfWorkFactory,
    mail_handlers: IdentityMailHandlers,
    mailer: InMemoryMailer,
    clock: FixedClock,
    engine: AsyncEngine,
) -> None:
    account = await register(identity, uow_factory)
    event = registered_event(account, clock)
    await mail_handlers.send_verification_mail(event)

    (mail,) = mailer.sent
    assert mail.to == EMAIL
    assert mail.subject == "Bitte bestätige deine E-Mail-Adresse"
    assert mail.text.startswith("Hallo Erika,")
    assert f"willkommen bei {SHOP_NAME}!" in mail.text
    assert f"{PUBLIC_BASE_URL}/konto/bestaetigen?token=" in mail.text
    token = token_from(mail)
    assert token in mail.html

    async with uow_factory() as uow:
        stored = await uow.tokens.get(hash_token(token))
    assert stored is not None
    assert stored.source_event_id == event.event_id
    assert stored.created_at == clock.now()
    assert stored.expires_at == clock.now() + timedelta(hours=24)

    # At-least-once delivery: running the handler again sends nothing new.
    await mail_handlers.send_verification_mail(event)
    assert len(mailer.sent) == 1
    assert await token_count(engine) == 1


async def test_failed_mail_leaves_no_token_and_is_retried_with_a_new_one(
    identity: IdentityService,
    uow_factory: UnitOfWorkFactory,
    mail_handlers: IdentityMailHandlers,
    mailer: InMemoryMailer,
    clock: FixedClock,
    engine: AsyncEngine,
) -> None:
    account = await register(identity, uow_factory)
    event = registered_event(account, clock)
    failing = IdentityMailHandlers(
        uow_factory=uow_factory,
        mailer=FailingMailer(),
        clock=clock,
        public_base_url=PUBLIC_BASE_URL,
        shop_name=SHOP_NAME,
    )
    # The error must reach the dispatcher, which schedules a retry.
    with pytest.raises(ConnectionRefusedError):
        await failing.send_verification_mail(event)
    assert await token_count(engine) == 0

    await mail_handlers.send_verification_mail(event)
    assert len(mailer.sent) == 1
    assert await token_count(engine) == 1


async def test_no_verification_mail_for_verified_or_unknown_accounts(
    identity: IdentityService,
    uow_factory: UnitOfWorkFactory,
    mail_handlers: IdentityMailHandlers,
    mailer: InMemoryMailer,
    clock: FixedClock,
) -> None:
    account = await register(identity, uow_factory)
    async with uow_factory() as uow:
        stored = await uow.accounts.get(account.id)
        assert stored is not None
        stored.verify_email(clock.now())
        await uow.commit()
    await mail_handlers.send_verification_mail(registered_event(account, clock))

    unknown, _ = Account.register_customer(
        email="x@example.com", display_name="X", password_hash="h", now=clock.now()
    )
    await mail_handlers.send_verification_mail(registered_event(unknown, clock))
    assert mailer.sent == []


async def test_existing_account_mail_points_to_password_reset(
    identity: IdentityService,
    uow_factory: UnitOfWorkFactory,
    mail_handlers: IdentityMailHandlers,
    mailer: InMemoryMailer,
    clock: FixedClock,
    engine: AsyncEngine,
) -> None:
    account = await register(identity, uow_factory)
    await mail_handlers.send_existing_account_mail(
        RegistrationAttemptedForExistingAccount(aggregate_id=account.id, occurred_at=clock.now())
    )
    (mail,) = mailer.sent
    assert mail.subject == "Für diese Adresse gibt es schon ein Konto"
    assert f"{PUBLIC_BASE_URL}/konto/passwort-vergessen" in mail.text
    assert "token=" not in mail.text
    assert await token_count(engine) == 0


async def test_password_changed_notice_for_customers_and_staff(
    identity: IdentityService,
    uow_factory: UnitOfWorkFactory,
    mail_handlers: IdentityMailHandlers,
    mailer: InMemoryMailer,
    clock: FixedClock,
) -> None:
    customer = await register(identity, uow_factory)
    staff = await identity.create_staff(
        email="lager@example.com", display_name="Lager", role=StaffRole.PACKER, password=PASSWORD
    )
    for account in (customer, staff):
        await mail_handlers.send_password_changed_mail(
            PasswordChanged(aggregate_id=account.id, occurred_at=clock.now())
        )

    to_customer, to_staff = mailer.sent
    assert to_customer.subject == to_staff.subject == "Dein Passwort wurde geändert"
    assert "Wenn du das nicht warst" in to_customer.text
    assert f"{PUBLIC_BASE_URL}/konto/passwort-vergessen" in to_customer.text
    assert "Shop-Leitung" in to_staff.text
    assert "/konto/" not in to_staff.text


async def test_no_notice_for_deleted_accounts(
    identity: IdentityService,
    uow_factory: UnitOfWorkFactory,
    mail_handlers: IdentityMailHandlers,
    mailer: InMemoryMailer,
    clock: FixedClock,
) -> None:
    account = await register(identity, uow_factory)
    async with uow_factory() as uow:
        stored = await uow.accounts.get(account.id)
        assert stored is not None
        stored.delete(clock.now())
        await uow.commit()
    await mail_handlers.send_password_changed_mail(
        PasswordChanged(aggregate_id=account.id, occurred_at=clock.now())
    )
    assert mailer.sent == []
