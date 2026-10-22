"""Domain rules of the identity module, without a database."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from modellbahn.modules.identity.domain.errors import (
    InvalidDisplayNameError,
    InvalidTokenError,
    PasswordPolicyViolationError,
    PasswordRule,
)
from modellbahn.modules.identity.domain.events import (
    AccountDeleted,
    CustomerRegistered,
    EmailVerified,
    PasswordChanged,
)
from modellbahn.modules.identity.domain.model import (
    DELETED_DISPLAY_NAME,
    UNUSABLE_PASSWORD_HASH,
    Account,
    AccountKind,
    AccountStatus,
    AccountToken,
    LoginSession,
    StaffRole,
    TokenPurpose,
    check_password_policy,
    lockout_duration,
    normalize_display_name,
)

NOW = datetime(2026, 10, 22, 10, 0, tzinfo=UTC)


def customer(**changes: object) -> Account:
    account, _ = Account.register_customer(
        email="kunde@example.com", display_name="Erika Muster", password_hash="hash", now=NOW
    )
    for name, value in changes.items():
        setattr(account, name, value)
    return account


class TestPasswordPolicy:
    def test_accepts_ten_to_256_characters(self) -> None:
        check_password_policy("a" * 10, email="kunde@example.com")
        check_password_policy("ä" * 256, email="kunde@example.com")

    @pytest.mark.parametrize(
        ("password", "rule"),
        [
            ("a" * 9, PasswordRule.TOO_SHORT),
            ("a" * 257, PasswordRule.TOO_LONG),
            ("Kunde@Example.com", PasswordRule.EQUALS_EMAIL),
        ],
    )
    def test_rejects(self, password: str, rule: PasswordRule) -> None:
        with pytest.raises(PasswordPolicyViolationError) as caught:
            check_password_policy(password, email="kunde@example.com")
        assert caught.value.rule is rule


class TestDisplayName:
    def test_collapses_whitespace(self) -> None:
        assert normalize_display_name("  Erika \t Muster\n") == "Erika Muster"

    @pytest.mark.parametrize(
        "name", ["", "   ", "x" * 81, "Erika\x00", "Erika\x1b[31m", "Admin\u202eniw"]
    )
    def test_rejects(self, name: str) -> None:
        with pytest.raises(InvalidDisplayNameError):
            normalize_display_name(name)

    def test_accepts_80_characters_and_emoji_sequences(self) -> None:
        assert normalize_display_name("x" * 80) == "x" * 80
        family = "Familie \U0001f468\u200d\U0001f469\u200d\U0001f467"
        assert normalize_display_name(family) == family


class TestLockoutSchedule:
    @pytest.mark.parametrize("failures", [0, 1, 4, 6, 9, 11])
    def test_no_lock_between_every_fifth_failure(self, failures: int) -> None:
        assert lockout_duration(failures) is None

    @pytest.mark.parametrize(
        ("failures", "minutes"),
        [(5, 15), (10, 30), (15, 60), (20, 120), (25, 240), (30, 480), (35, 960)],
    )
    def test_doubles_with_every_lock(self, failures: int, minutes: int) -> None:
        assert lockout_duration(failures) == timedelta(minutes=minutes)

    @pytest.mark.parametrize("failures", [40, 45, 1000, 32_765])
    def test_is_capped_at_one_day(self, failures: int) -> None:
        assert lockout_duration(failures) == timedelta(hours=24)


class TestRegistration:
    def test_new_customer_is_active_unverified_and_announced(self) -> None:
        account, event = Account.register_customer(
            email="kunde@example.com", display_name=" Erika ", password_hash="hash", now=NOW
        )
        assert account.kind is AccountKind.CUSTOMER
        assert account.status is AccountStatus.ACTIVE
        assert account.role is None
        assert account.display_name == "Erika"
        assert account.needs_email_verification
        assert isinstance(event, CustomerRegistered)
        assert event.aggregate_id == account.id
        assert event.public_payload() == {"account_id": str(account.id), "display_name": "Erika"}

    def test_staff_has_a_role_and_needs_no_verification(self) -> None:
        account = Account.create_staff(
            email="chefin@example.com",
            display_name="Chefin",
            role=StaffRole.OWNER,
            password_hash="hash",
            now=NOW,
        )
        assert account.kind is AccountKind.STAFF
        assert account.role is StaffRole.OWNER
        assert not account.needs_email_verification


class TestLogin:
    def test_fifth_failure_locks_for_fifteen_minutes(self) -> None:
        account = customer()
        for _ in range(4):
            account.record_failed_login(NOW)
        assert not account.is_locked(NOW)
        account.record_failed_login(NOW)
        assert account.locked_until == NOW + timedelta(minutes=15)
        assert account.is_locked(NOW + timedelta(minutes=14))
        assert not account.is_locked(NOW + timedelta(minutes=15))

    def test_success_resets_failures_and_lock(self) -> None:
        account = customer(failed_login_count=5, locked_until=NOW)
        account.record_successful_login(NOW + timedelta(minutes=20))
        assert account.failed_login_count == 0
        assert account.locked_until is None
        assert account.last_login_at == NOW + timedelta(minutes=20)

    def test_second_lock_lasts_twice_as_long(self) -> None:
        account = customer(failed_login_count=9)
        account.record_failed_login(NOW)
        assert account.locked_until == NOW + timedelta(minutes=30)

    def test_correct_password_clears_failures(self) -> None:
        account = customer(failed_login_count=3)
        account.record_correct_password(NOW)
        assert account.failed_login_count == 0


class TestStateTransitions:
    def test_verify_email_announces_only_once(self) -> None:
        account = customer()
        first = account.verify_email(NOW)
        assert isinstance(first, EmailVerified)
        assert first.public_payload()["display_name"] == "Erika Muster"
        assert account.verify_email(NOW + timedelta(hours=1)) is None
        assert account.email_verified_at == NOW

    def test_reset_password_verifies_and_unlocks(self) -> None:
        account = customer(failed_login_count=5, locked_until=NOW + timedelta(minutes=15))
        events = account.reset_password("new-hash", NOW)
        assert [type(event) for event in events] == [PasswordChanged, EmailVerified]
        assert account.password_hash == "new-hash"
        assert account.email_verified
        assert not account.is_locked(NOW)

    def test_reset_password_of_verified_account_only_changes_password(self) -> None:
        account = customer(email_verified_at=NOW)
        assert [type(event) for event in account.reset_password("x", NOW)] == [PasswordChanged]

    def test_rename_validates(self) -> None:
        account = customer()
        account.rename("  Erika  Mustermann ", NOW + timedelta(seconds=1))
        assert account.display_name == "Erika Mustermann"
        assert account.updated_at == NOW + timedelta(seconds=1)
        with pytest.raises(InvalidDisplayNameError):
            account.rename("", NOW)

    def test_verification_mail_only_for_unverified_active_customers(self) -> None:
        assert customer().request_verification_mail(NOW) is not None
        assert customer(email_verified_at=NOW).request_verification_mail(NOW) is None
        assert customer(status=AccountStatus.DELETED).request_verification_mail(NOW) is None

    def test_password_reset_only_for_active_customers(self) -> None:
        assert customer().request_password_reset(NOW) is not None
        assert customer(status=AccountStatus.DELETED).request_password_reset(NOW) is None
        staff = Account.create_staff(
            email="a@example.com",
            display_name="A",
            role=StaffRole.PACKER,
            password_hash="h",
            now=NOW,
        )
        assert staff.request_password_reset(NOW) is None


class TestDeletion:
    def test_anonymises_the_account(self) -> None:
        account = customer(failed_login_count=3)
        event = account.delete(NOW)
        assert isinstance(event, AccountDeleted)
        assert account.status is AccountStatus.DELETED
        assert account.email == f"deleted+{account.id}@invalid.local"
        assert account.display_name == DELETED_DISPLAY_NAME
        assert account.password_hash == UNUSABLE_PASSWORD_HASH
        assert account.failed_login_count == 0
        assert not account.is_active


class TestLoginSession:
    @pytest.mark.parametrize(
        ("kind", "lifetime"),
        [(AccountKind.CUSTOMER, timedelta(days=30)), (AccountKind.STAFF, timedelta(hours=12))],
    )
    def test_lifetime_depends_on_area(self, kind: AccountKind, lifetime: timedelta) -> None:
        account = customer(kind=kind, role=StaffRole.STAFF if kind is AccountKind.STAFF else None)
        session = LoginSession.start(account=account, token_hash="0" * 64, now=NOW, user_agent=None)
        assert session.kind is kind
        assert session.expires_at == NOW + lifetime
        assert not session.is_expired(NOW + lifetime - timedelta(seconds=1))
        assert session.is_expired(NOW + lifetime)

    def test_touch_at_most_every_five_minutes(self) -> None:
        session = LoginSession.start(
            account=customer(), token_hash="0" * 64, now=NOW, user_agent="x" * 1000
        )
        assert session.user_agent is not None
        assert len(session.user_agent) == 512
        assert not session.touch(NOW + timedelta(minutes=4, seconds=59))
        assert session.touch(NOW + timedelta(minutes=5))
        assert session.last_seen_at == NOW + timedelta(minutes=5)


class TestAccountToken:
    @pytest.mark.parametrize(
        ("purpose", "lifetime"),
        [
            (TokenPurpose.VERIFY_EMAIL, timedelta(hours=24)),
            (TokenPurpose.RESET_PASSWORD, timedelta(hours=1)),
        ],
    )
    def test_lifetime_depends_on_purpose(self, purpose: TokenPurpose, lifetime: timedelta) -> None:
        token = AccountToken.issue(
            token_hash="0" * 64, account_id=uuid4(), purpose=purpose, now=NOW, source_event_id=None
        )
        assert token.expires_at == NOW + lifetime

    def test_redeemable_once_for_its_purpose_until_expiry(self) -> None:
        def issue() -> AccountToken:
            return AccountToken.issue(
                token_hash="0" * 64,
                account_id=uuid4(),
                purpose=TokenPurpose.RESET_PASSWORD,
                now=NOW,
                source_event_id=None,
            )

        with pytest.raises(InvalidTokenError):
            issue().redeem(TokenPurpose.VERIFY_EMAIL, NOW)
        with pytest.raises(InvalidTokenError):
            issue().redeem(TokenPurpose.RESET_PASSWORD, NOW + timedelta(hours=1))

        token = issue()
        token.redeem(TokenPurpose.RESET_PASSWORD, NOW)
        assert token.used_at == NOW
        with pytest.raises(InvalidTokenError):
            token.redeem(TokenPurpose.RESET_PASSWORD, NOW)
