"""eBay's signature on its notifications (the ``X-EBAY-SIGNATURE`` header).

The header is Base64 of a small JSON object: the algorithm (ECDSA), the id of eBay's
public key, the signature (Base64 of DER) and the digest (SHA1). The key comes from
eBay's Notification API by its id and is kept, as eBay's own SDKs do.

The signature covers the notification as JSON. eBay's SDKs check it over the body
parsed and serialised again without spaces; the body as received is tried first, then
that form, so a sender that adds spaces does not turn a genuine notification away.
"""

import base64
import binascii
import json
from collections import OrderedDict
from dataclasses import dataclass
from typing import Final, Protocol

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from modellbahn.modules.marketplace.application.ports import (
    MarketplaceRejectedError,
    NotificationKey,
)

_ALGORITHM: Final = "ECDSA"
_DIGESTS: Final[dict[str, type[hashes.HashAlgorithm]]] = {
    "SHA1": hashes.SHA1,
    "SHA256": hashes.SHA256,
}
_KEYS_KEPT: Final = 16
_HEADER_MAX_LENGTH: Final = 4096
_PEM_MARKERS: Final = ("-----BEGIN PUBLIC KEY-----", "-----END PUBLIC KEY-----")


class NotificationKeySource(Protocol):
    async def notification_key(self, key_id: str) -> NotificationKey: ...


@dataclass(frozen=True, slots=True)
class _Header:
    key_id: str
    signature: bytes
    digest: str


class EcdsaNotificationSignatures:
    """Checks notifications against eBay's public keys, fetched once per key id."""

    def __init__(self, keys: NotificationKeySource) -> None:
        self._keys = keys
        self._loaded: OrderedDict[str, ec.EllipticCurvePublicKey | None] = OrderedDict()

    async def verify(self, body: bytes, signature: str) -> bool:
        header = _header(signature)
        if header is None:
            return False
        digest = _DIGESTS.get(header.digest.upper())
        public_key = await self._key(header.key_id)
        if digest is None or public_key is None:
            return False
        for message in _messages(body):
            try:
                public_key.verify(header.signature, message, ec.ECDSA(digest()))
            except InvalidSignature:
                continue
            return True
        return False

    async def _key(self, key_id: str) -> ec.EllipticCurvePublicKey | None:
        if key_id in self._loaded:
            self._loaded.move_to_end(key_id)
            return self._loaded[key_id]
        try:
            key = _public_key(await self._keys.notification_key(key_id))
        except MarketplaceRejectedError:
            # eBay knows no such key: a made-up id. Not kept, or ids could flood the cache.
            return None
        self._loaded[key_id] = key
        while len(self._loaded) > _KEYS_KEPT:
            self._loaded.popitem(last=False)
        return key


def _header(signature: str) -> _Header | None:
    if not signature or len(signature) > _HEADER_MAX_LENGTH:
        return None
    try:
        fields = json.loads(base64.b64decode(signature, validate=True))
        key_id = fields["kid"]
        signed = base64.b64decode(fields["signature"], validate=True)
        algorithm = fields.get("alg", "")
        digest = fields.get("digest", "")
    except (binascii.Error, ValueError, TypeError, KeyError):
        return None
    if not isinstance(key_id, str) or not key_id or not isinstance(digest, str):
        return None
    if not isinstance(algorithm, str) or algorithm.upper() != _ALGORITHM:
        return None
    return _Header(key_id=key_id, signature=signed, digest=digest)


def _public_key(key: NotificationKey) -> ec.EllipticCurvePublicKey | None:
    if key.algorithm.upper() != _ALGORITHM:
        return None
    text = key.pem
    for marker in _PEM_MARKERS:
        text = text.replace(marker, "")
    try:
        loaded = serialization.load_der_public_key(base64.b64decode("".join(text.split())))
    except (binascii.Error, ValueError, UnsupportedAlgorithm):
        return None
    return loaded if isinstance(loaded, ec.EllipticCurvePublicKey) else None


def _messages(body: bytes) -> list[bytes]:
    """The body as received, and as eBay's SDKs serialise it again."""
    try:
        compact = json.dumps(json.loads(body), separators=(",", ":"), ensure_ascii=False).encode()
    except (UnicodeDecodeError, ValueError):
        return [body]
    return [body] if compact == body else [body, compact]
