"""Media events and the types they carry, for other modules to react to.

Plain Python like the domain it comes from: importing it keeps a domain layer pure.
"""

from modellbahn.modules.media.domain.errors import FailureCode
from modellbahn.modules.media.domain.events import AssetDeleted, AssetFailed, AssetReady
from modellbahn.modules.media.domain.model import AssetKind, AssetStatus

__all__ = [
    "AssetDeleted",
    "AssetFailed",
    "AssetKind",
    "AssetReady",
    "AssetStatus",
    "FailureCode",
]
