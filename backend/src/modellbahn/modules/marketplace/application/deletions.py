"""eBay's notifications that a user closed their account (ADR 0015).

eBay sends them to every app with production keys, for every account closed anywhere on
eBay; nearly all name strangers. Nothing about those is stored or logged: the user name
only finds the shop's own orders of that buyer, and their personal data goes.

eBay checks the endpoint before it enables the keys: it asks with a challenge code, and
the answer is the SHA-256 of the code, the verification token and the endpoint's address,
in that order. Without eBay (``MB_EBAY_MODE=off``) no signature can be checked; that is
fine as long as no order holds buyer data, which is the case while the keys are pending.
"""

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC
from enum import StrEnum
from typing import Any, Final
from uuid import uuid4

import structlog

from modellbahn.modules.marketplace.application.ports import (
    NotificationSignatures,
    UnitOfWorkFactory,
)
from modellbahn.modules.marketplace.domain.errors import (
    DeletionEndpointNotReadyError,
    DeletionsUnverifiableError,
    NotificationInvalidError,
    NotificationSignatureError,
    TestModeOnlyError,
)
from modellbahn.modules.marketplace.domain.model import EBAY
from modellbahn.platform.clock import Clock

_logger = structlog.get_logger(__name__)

ACCOUNT_DELETION_TOPIC: Final = "MARKETPLACE_ACCOUNT_DELETION"


@dataclass(frozen=True, slots=True)
class TestBuyer:
    """The test marketplace's buyer, and the test key that signs as eBay would."""

    name: str
    sign: Callable[[bytes], str]


class DeletionOutcome(StrEnum):
    ERASED = "erased"
    """Orders of this buyer lost their personal data."""
    UNKNOWN_BUYER = "unknown_buyer"
    """Not a buyer of the shop (or erased before): the usual case."""
    OTHER_TOPIC = "other_topic"
    NOTHING_HELD = "nothing_held"
    """eBay is off and no order holds buyer data: there is nothing to delete."""


@dataclass(frozen=True, slots=True)
class DeletionReceipt:
    outcome: DeletionOutcome
    erased_orders: int = 0


@dataclass(frozen=True, slots=True)
class _Notification:
    notification_id: str
    topic: str
    username: str


class AccountDeletionService:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        signatures: NotificationSignatures | None,
        verification_token: str,
        endpoint: str,
        clock: Clock,
        test_buyer: TestBuyer | None = None,
    ) -> None:
        self._uow = uow_factory
        self._signatures = signatures
        self._token = verification_token
        self._endpoint = endpoint
        self._clock = clock
        self._test_buyer = test_buyer

    @property
    def endpoint(self) -> str:
        """The address to enter in eBay's developer account, exactly as written."""
        return self._endpoint

    @property
    def ready(self) -> bool:
        """Whether eBay's check of the endpoint can be answered."""
        return bool(self._token)

    @property
    def checks_signatures(self) -> bool:
        """False while eBay is off: then no key of eBay's can be fetched."""
        return self._signatures is not None

    @property
    def test_buyer_name(self) -> str | None:
        return self._test_buyer.name if self._test_buyer is not None else None

    def challenge_response(self, challenge_code: str) -> str:
        if not self._token:
            raise DeletionEndpointNotReadyError
        digest = hashlib.sha256()
        for part in (challenge_code, self._token, self._endpoint):
            digest.update(part.encode())
        return digest.hexdigest()

    async def receive(self, body: bytes, signature: str) -> DeletionReceipt:
        notification = _parse(body)
        if self._signatures is None:
            async with self._uow() as uow:
                held = await uow.orders.hold_buyer_data(EBAY)
            if held:
                raise DeletionsUnverifiableError
            return DeletionReceipt(DeletionOutcome.NOTHING_HELD)
        if not signature or not await self._signatures.verify(body, signature):
            _logger.warning(
                "marketplace.ebay.notification_unsigned",
                notification_id=notification.notification_id,
            )
            raise NotificationSignatureError
        if notification.topic != ACCOUNT_DELETION_TOPIC:
            return DeletionReceipt(DeletionOutcome.OTHER_TOPIC)
        now = self._clock.now()
        async with self._uow() as uow:
            orders = await uow.orders.of_buyer(EBAY, notification.username)
            erased = sum(order.erase_buyer(now) for order in orders)
            await uow.commit()
        if not erased:
            return DeletionReceipt(DeletionOutcome.UNKNOWN_BUYER)
        # No user name: the log must not keep what was just deleted.
        _logger.info(
            "marketplace.ebay.buyer_erased",
            notification_id=notification.notification_id,
            orders=erased,
        )
        return DeletionReceipt(DeletionOutcome.ERASED, erased_orders=erased)

    async def close_test_account(self) -> DeletionReceipt:
        """The test marketplace's buyer closes their account: eBay's notification, signed
        with the test key, through the same checks as a real one."""
        if self._test_buyer is None:
            raise TestModeOnlyError
        buyer_name = self._test_buyer.name
        now = self._clock.now().astimezone(UTC)
        moment = now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"
        body = json.dumps(
            {
                "metadata": {
                    "topic": ACCOUNT_DELETION_TOPIC,
                    "schemaVersion": "1.0",
                    "deprecated": False,
                },
                "notification": {
                    "notificationId": str(uuid4()),
                    "eventDate": moment,
                    "publishDate": moment,
                    "publishAttemptCount": 1,
                    "data": {
                        "username": buyer_name,
                        "userId": f"test-{hashlib.sha256(buyer_name.encode()).hexdigest()[:11]}",
                        "eiasToken": "",
                    },
                },
            },
            separators=(",", ":"),
        ).encode()
        return await self.receive(body, self._test_buyer.sign(body))


def _parse(body: bytes) -> _Notification:
    try:
        message: Any = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NotificationInvalidError from exc
    metadata = _object(message, "metadata")
    notification = _object(message, "notification")
    data = notification.get("data")
    topic = metadata.get("topic")
    notification_id = notification.get("notificationId")
    if not isinstance(topic, str) or not isinstance(notification_id, str):
        raise NotificationInvalidError
    username = data.get("username") if isinstance(data, Mapping) else None
    if topic == ACCOUNT_DELETION_TOPIC and not (isinstance(username, str) and username):
        raise NotificationInvalidError
    return _Notification(
        notification_id=notification_id[:200],
        topic=topic,
        username=username if isinstance(username, str) else "",
    )


def _object(message: Any, key: str) -> Mapping[str, Any]:
    value = message.get(key) if isinstance(message, Mapping) else None
    if not isinstance(value, Mapping):
        raise NotificationInvalidError
    return value
