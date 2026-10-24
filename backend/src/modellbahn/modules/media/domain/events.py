"""Domain events of the media module.

``ready`` and ``failed`` reach the admin area live, so a gallery swaps its placeholder
for the thumbnail without reloading. Their public payload is only the asset id (and
the failure code): the page fetches the asset itself.
"""

from dataclasses import dataclass
from typing import ClassVar, Final

from modellbahn.modules.media.domain.errors import FailureCode
from modellbahn.platform.events import DomainEvent, JsonObject, domain_event

ASSET_AGGREGATE: Final = "media.asset"
STAFF_AUDIENCE: Final = frozenset({"staff"})


@domain_event
@dataclass(frozen=True, kw_only=True)
class AssetUploaded(DomainEvent):
    """The original arrived in the private storage; the worker renders the sizes."""

    event_type: ClassVar[str] = "media.asset.uploaded"
    aggregate_type: ClassVar[str] = ASSET_AGGREGATE


@domain_event
@dataclass(frozen=True, kw_only=True)
class AssetReady(DomainEvent):
    """All sizes are rendered and public; the asset can be shown in the shop."""

    event_type: ClassVar[str] = "media.asset.ready"
    aggregate_type: ClassVar[str] = ASSET_AGGREGATE
    audience: ClassVar[frozenset[str]] = STAFF_AUDIENCE

    def public_payload(self) -> JsonObject:
        return {"asset_id": str(self.aggregate_id)}


@domain_event
@dataclass(frozen=True, kw_only=True)
class AssetFailed(DomainEvent):
    """Processing gave up: the file is unusable, or every attempt failed."""

    event_type: ClassVar[str] = "media.asset.failed"
    aggregate_type: ClassVar[str] = ASSET_AGGREGATE
    audience: ClassVar[frozenset[str]] = STAFF_AUDIENCE

    failure_code: FailureCode

    def public_payload(self) -> JsonObject:
        return {"asset_id": str(self.aggregate_id), "failure_code": self.failure_code.value}


@domain_event
@dataclass(frozen=True, kw_only=True)
class AssetDeleted(DomainEvent):
    """The asset is gone from the database; the worker removes its files from the storage."""

    event_type: ClassVar[str] = "media.asset.deleted"
    aggregate_type: ClassVar[str] = ASSET_AGGREGATE
