"""Identity use cases against PostgreSQL, with a controllable clock and the real outbox."""

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from modellbahn.modules.identity.application.services import IdentityService, UnitOfWorkFactory
from modellbahn.modules.identity.domain.errors import (
    AccountAlreadyExistsError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    InvalidPasswordError,
    InvalidTokenError,
    NotAuthenticatedError,
    PasswordPolicyViolationError,
)
from modellbahn.modules.identity.domain.model import Account, AccountKind, AccountStatus, StaffRole
from modellbahn.modules.identity.infrastructure.tables import account_tokens
from modellbahn.platform.clock import FixedClock
from modellbahn.platform.mail import InMemoryMailer
from modellbahn.platform.outbox import outbox_table
from modellbahn.platform.security import Argon2PasswordHasher
from tests.conftest import Deliver
from tests.support import token_from

EMAIL = "kunde@example.com"
PASSWORD = "Gleis 7 und Weiche 3"
NEW_PASSWORD = "Neues sicheres Passwort"
WRONG = "falsches Passwort"


async def event_types(engine: AsyncEngine) -> list[str]:
    async with engine.connect() as connection:
        rows = await connection.scalars(
            select(outbox_table.c.event_type).order_by(outbox_table.c.id)
        )
        return list(rows)


async def load(uow_factory: UnitOfWorkFactory, email: str = EMAIL) -> Account:
    async with uow_factory() as uow:
        account = await uow.accounts.get_by_email(AccountKind.CUSTOMER, email)
    assert account is not None
    return account


async def login(identity: IdentityService, password: str = PASSWORD) -> str:
    started = await identity.login(
        kind=AccountKind.CUSTOMER, email=EMAIL, password=password, user_agent="pytest"
    )
    return started.token


@pytest.fixture
async def verified(identity: IdentityService, deliver: Deliver, mailer: InMemoryMailer) -> str:
    """A registered and verified customer; the value is its session token."""
    await identity.register_customer(email=EMAIL, password=PASSWORD, display_name="Erika")
    await deliver()
    started = await identity.verify_email(token=token_from(mailer.sent[-1]), user_agent="pytest")
    return started.token


class TestRegistration:
    async def test_new_and_existing_address_answer_alike_but_differ_inside(
        self, identity: IdentityService, engine: AsyncEngine, uow_factory: UnitOfWorkFactory
    ) -> None:
        await identity.register_customer(email=EMAIL, password=PASSWORD, display_name="Erika")
        await identity.register_customer(
            email="KUNDE@example.com", password="anderes Passwort", display_name="Mallory"
        )
        assert await event_types(engine) == [
            "identity.customer.registered",
            "identity.customer.registration_attempted_existing",
        ]
        account = await load(uow_factory)
        assert account.display_name == "Erika"
        assert account.status is AccountStatus.ACTIVE
        assert not account.email_verified

    async def test_concurrent_registrations_create_one_account(
        self, identity: IdentityService, engine: AsyncEngine
    ) -> None:
        await asyncio.gather(
            *(
                identity.register_customer(email=EMAIL, password=PASSWORD, display_name="Erika")
                for _ in range(4)
            )
        )
        types = await event_types(engine)
        assert types.count("identity.customer.registered") == 1
        assert types.count("identity.customer.registration_attempted_existing") == 3

    async def test_policy_is_checked_before_anything_happens(
        self, identity: IdentityService, engine: AsyncEngine
    ) -> None:
        with pytest.raises(PasswordPolicyViolationError):
            await identity.register_customer(email=EMAIL, password=EMAIL, display_name="Erika")
        assert await event_types(engine) == []


class TestVerification:
    async def test_verification_logs_in_and_works_once(
        self,
        identity: IdentityService,
        deliver: Deliver,
        mailer: InMemoryMailer,
        engine: AsyncEngine,
    ) -> None:
        await identity.register_customer(email=EMAIL, password=PASSWORD, display_name="Erika")
        await deliver()
        token = token_from(mailer.sent[-1])

        started = await identity.verify_email(token=token, user_agent="pytest")
        assert started.account.email_verified
        auth = await identity.authenticate(kind=AccountKind.CUSTOMER, token=started.token)
        assert auth.account.id == started.account.id
        assert (await event_types(engine))[-1] == "identity.account.email_verified"
        with pytest.raises(InvalidTokenError):
            await identity.verify_email(token=token, user_agent=None)

    async def test_verifying_invalidates_the_other_links(
        self, identity: IdentityService, deliver: Deliver, mailer: InMemoryMailer
    ) -> None:
        await identity.register_customer(email=EMAIL, password=PASSWORD, display_name="Erika")
        await identity.request_verification_mail(email=EMAIL)
        await deliver()
        first, second = (token_from(mail) for mail in mailer.sent)
        await identity.verify_email(token=second, user_agent=None)
        # Each link logs in, so the unused one must not keep working.
        with pytest.raises(InvalidTokenError):
            await identity.verify_email(token=first, user_agent=None)

    async def test_expired_or_unknown_tokens_are_rejected(
        self,
        identity: IdentityService,
        deliver: Deliver,
        mailer: InMemoryMailer,
        clock: FixedClock,
    ) -> None:
        await identity.register_customer(email=EMAIL, password=PASSWORD, display_name="Erika")
        await deliver()
        clock.advance(timedelta(hours=24))
        with pytest.raises(InvalidTokenError):
            await identity.verify_email(token=token_from(mailer.sent[-1]), user_agent=None)
        with pytest.raises(InvalidTokenError):
            await identity.verify_email(token="unknown", user_agent=None)

    async def test_resend_only_for_unverified_customers(
        self, identity: IdentityService, verified: str, engine: AsyncEngine
    ) -> None:
        before = await event_types(engine)
        await identity.request_verification_mail(email=EMAIL)
        await identity.request_verification_mail(email="niemand@example.com")
        assert await event_types(engine) == before

        await identity.register_customer(
            email="neu@example.com", password=PASSWORD, display_name="Neu"
        )
        await identity.request_verification_mail(email="neu@example.com")
        assert (await event_types(engine))[-1] == "identity.customer.verification_requested"


class TestLogin:
    async def test_unverified_customer_is_told_only_after_the_right_password(
        self, identity: IdentityService
    ) -> None:
        await identity.register_customer(email=EMAIL, password=PASSWORD, display_name="Erika")
        with pytest.raises(InvalidCredentialsError):
            await login(identity, WRONG)
        with pytest.raises(EmailNotVerifiedError):
            await login(identity)

    async def test_unknown_address(self, identity: IdentityService) -> None:
        with pytest.raises(InvalidCredentialsError):
            await login(identity)

    async def test_lockout_and_its_expiry(
        self,
        identity: IdentityService,
        verified: str,
        uow_factory: UnitOfWorkFactory,
        clock: FixedClock,
    ) -> None:
        for _ in range(5):
            with pytest.raises(InvalidCredentialsError):
                await login(identity, WRONG)
        # Locked: even the right password is refused, exactly like a wrong one.
        with pytest.raises(InvalidCredentialsError):
            await login(identity)
        assert (await load(uow_factory)).failed_login_count == 5

        clock.advance(timedelta(minutes=15))
        await login(identity)
        account = await load(uow_factory)
        assert account.failed_login_count == 0
        assert account.locked_until is None

    async def test_outdated_hashes_are_upgraded_on_login(
        self,
        verified: str,
        uow_factory: UnitOfWorkFactory,
        clock: FixedClock,
    ) -> None:
        old_hash = (await load(uow_factory)).password_hash
        stronger = IdentityService(
            uow_factory=uow_factory,
            hasher=Argon2PasswordHasher(time_cost=2, memory_cost=16, parallelism=1),
            clock=clock,
        )
        await login(stronger)
        new_hash = (await load(uow_factory)).password_hash
        assert new_hash != old_hash
        assert "m=16,t=2" in new_hash

    async def test_sessions_expire_and_are_touched_sparingly(
        self,
        identity: IdentityService,
        verified: str,
        uow_factory: UnitOfWorkFactory,
        clock: FixedClock,
    ) -> None:
        auth = await identity.authenticate(kind=AccountKind.CUSTOMER, token=verified)
        started_at = clock.now()

        clock.advance(timedelta(minutes=4))
        await identity.authenticate(kind=AccountKind.CUSTOMER, token=verified)
        async with uow_factory() as uow:
            session = await uow.sessions.get(auth.session_token_hash)
            assert session is not None
            assert session.last_seen_at == started_at

        clock.advance(timedelta(minutes=2))
        await identity.authenticate(kind=AccountKind.CUSTOMER, token=verified)
        async with uow_factory() as uow:
            session = await uow.sessions.get(auth.session_token_hash)
            assert session is not None
            assert session.last_seen_at == clock.now()

        clock.advance(timedelta(days=30))
        with pytest.raises(NotAuthenticatedError):
            await identity.authenticate(kind=AccountKind.CUSTOMER, token=verified)
        async with uow_factory() as uow:
            assert await uow.sessions.get(auth.session_token_hash) is None

    async def test_sessions_belong_to_one_area(
        self, identity: IdentityService, verified: str
    ) -> None:
        with pytest.raises(NotAuthenticatedError):
            await identity.authenticate(kind=AccountKind.STAFF, token=verified)
        await identity.logout(kind=AccountKind.STAFF, token=verified)
        await identity.authenticate(kind=AccountKind.CUSTOMER, token=verified)
        await identity.logout(kind=AccountKind.CUSTOMER, token=verified)
        with pytest.raises(NotAuthenticatedError):
            await identity.authenticate(kind=AccountKind.CUSTOMER, token=verified)


class TestPasswords:
    async def test_change_password_keeps_only_the_current_session(
        self, identity: IdentityService, verified: str, engine: AsyncEngine
    ) -> None:
        other = await login(identity)
        auth = await identity.authenticate(kind=AccountKind.CUSTOMER, token=verified)

        with pytest.raises(InvalidPasswordError):
            await identity.change_password(
                account_id=auth.account.id,
                session_token_hash=auth.session_token_hash,
                current_password=WRONG,
                new_password=NEW_PASSWORD,
            )
        await identity.change_password(
            account_id=auth.account.id,
            session_token_hash=auth.session_token_hash,
            current_password=PASSWORD,
            new_password=NEW_PASSWORD,
        )
        await identity.authenticate(kind=AccountKind.CUSTOMER, token=verified)
        with pytest.raises(NotAuthenticatedError):
            await identity.authenticate(kind=AccountKind.CUSTOMER, token=other)
        assert (await event_types(engine))[-1] == "identity.account.password_changed"
        await login(identity, NEW_PASSWORD)

    async def test_wrong_confirmations_count_towards_the_lockout(
        self, identity: IdentityService, verified: str, uow_factory: UnitOfWorkFactory
    ) -> None:
        auth = await identity.authenticate(kind=AccountKind.CUSTOMER, token=verified)
        for _ in range(6):
            with pytest.raises(InvalidPasswordError):
                await identity.delete_account(account_id=auth.account.id, password=WRONG)
        # Now locked: even the right password does not confirm anything.
        with pytest.raises(InvalidPasswordError):
            await identity.delete_account(account_id=auth.account.id, password=PASSWORD)
        assert (await load(uow_factory)).failed_login_count == 5

    async def test_reset_password_flow(
        self,
        identity: IdentityService,
        deliver: Deliver,
        mailer: InMemoryMailer,
        engine: AsyncEngine,
    ) -> None:
        # Unverified on purpose: receiving the reset link proves the address, too.
        await identity.register_customer(email=EMAIL, password=PASSWORD, display_name="Erika")
        await identity.request_password_reset(email=EMAIL)
        await identity.request_password_reset(email="niemand@example.com")
        await deliver()
        token = token_from(mailer.sent[-1])
        assert mailer.sent[-1].subject == "Neues Passwort festlegen"

        with pytest.raises(PasswordPolicyViolationError):
            await identity.reset_password(token=token, new_password=EMAIL)
        await identity.reset_password(token=token, new_password=NEW_PASSWORD)
        with pytest.raises(InvalidTokenError):
            await identity.reset_password(token=token, new_password=NEW_PASSWORD)

        assert (await event_types(engine))[-2:] == [
            "identity.account.password_changed",
            "identity.account.email_verified",
        ]
        await login(identity, NEW_PASSWORD)
        # The verification link from the first mail died with the reset.
        with pytest.raises(InvalidTokenError):
            await identity.verify_email(token=token_from(mailer.sent[0]), user_agent=None)

    async def test_reset_token_cannot_verify_and_vice_versa(
        self, identity: IdentityService, deliver: Deliver, mailer: InMemoryMailer
    ) -> None:
        await identity.register_customer(email=EMAIL, password=PASSWORD, display_name="Erika")
        await deliver()
        with pytest.raises(InvalidTokenError):
            await identity.reset_password(
                token=token_from(mailer.sent[-1]), new_password=NEW_PASSWORD
            )


class TestDeletionAndStaff:
    async def test_delete_account_anonymises_and_ends_sessions(
        self,
        identity: IdentityService,
        verified: str,
        uow_factory: UnitOfWorkFactory,
        engine: AsyncEngine,
    ) -> None:
        auth = await identity.authenticate(kind=AccountKind.CUSTOMER, token=verified)
        await identity.delete_account(account_id=auth.account.id, password=PASSWORD)

        with pytest.raises(NotAuthenticatedError):
            await identity.authenticate(kind=AccountKind.CUSTOMER, token=verified)
        async with uow_factory() as uow:
            deleted = await uow.accounts.get(auth.account.id)
        assert deleted is not None
        assert deleted.status is AccountStatus.DELETED
        assert deleted.email == f"deleted+{deleted.id}@invalid.local"
        async with engine.connect() as connection:
            tokens = await connection.scalar(
                select(func.count())
                .select_from(account_tokens)
                .where(account_tokens.c.account_id == deleted.id)
            )
        assert tokens == 0
        assert (await event_types(engine))[-1] == "identity.account.deleted"
        with pytest.raises(NotAuthenticatedError):
            await identity.rename(account_id=deleted.id, display_name="Wieder da")

        # The address is free again.
        await identity.register_customer(email=EMAIL, password=PASSWORD, display_name="Neu")
        assert (await event_types(engine))[-1] == "identity.customer.registered"

    async def test_create_staff(self, identity: IdentityService) -> None:
        staff = await identity.create_staff(
            email="chefin@example.com",
            display_name="Chefin",
            role=StaffRole.OWNER,
            password=PASSWORD,
        )
        assert staff.role is StaffRole.OWNER
        with pytest.raises(AccountAlreadyExistsError):
            await identity.create_staff(
                email="CHEFIN@example.com",
                display_name="Doppelt",
                role=StaffRole.STAFF,
                password=PASSWORD,
            )
        started = await identity.login(
            kind=AccountKind.STAFF, email="chefin@example.com", password=PASSWORD, user_agent=None
        )
        assert started.account.id == staff.id
        # Staff and customer accounts are separate, even for the same address.
        with pytest.raises(InvalidCredentialsError):
            await identity.login(
                kind=AccountKind.CUSTOMER,
                email="chefin@example.com",
                password=PASSWORD,
                user_agent=None,
            )
