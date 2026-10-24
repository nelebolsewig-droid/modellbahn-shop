"""Sets up a Garage node for the shop through its admin API (v2): layout, key, buckets.

Used by ``python -m modellbahn.cli init-storage``, which the Compose job
``storage-init`` runs on every start. Every step checks first and changes only what
is missing, so running it again is harmless. Other S3 services are set up by hand:
two buckets, a key with read and write access to both, website access on the public one.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Final

# A single node holds everything; the capacity only weighs nodes against each other.
NODE_CAPACITY_BYTES: Final = 100 * 1000**3
NODE_ZONE: Final = "local"
REQUEST_TIMEOUT_SECONDS: Final = 10.0
KEY_NAME: Final = "modellbahn-backend"


class GarageAdminError(Exception):
    """The admin API refused a request or answered unexpectedly."""


@dataclass(frozen=True, slots=True)
class StorageLayout:
    """What the shop needs from the storage."""

    access_key_id: str
    secret_access_key: str
    private_bucket: str
    public_bucket: str


class GarageAdmin:
    """A small client for the endpoints of the admin API that the set-up needs."""

    def __init__(self, base_url: str, token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token

    def wait_until_reachable(self, *, timeout_seconds: float) -> None:
        """Poll until the node answers; it may still be starting next to this job."""
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                self.call("GET", "GetClusterStatus")
            except (OSError, GarageAdminError):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(1)
            else:
                return

    def call(
        self,
        method: str,
        endpoint: str,
        *,
        query: dict[str, str] | None = None,
        body: object = None,
        missing_ok: bool = False,
    ) -> Any:
        """Call ``/v2/{endpoint}``; ``None`` for a 404 if ``missing_ok``."""
        url = f"{self._base_url}/v2/{endpoint}"
        if query:
            url += "?" + urllib.parse.urlencode(query)
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(url, data=data, method=method)  # noqa: S310
        request.add_header("Authorization", f"Bearer {self._token}")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310
                raw = response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and missing_ok:  # noqa: PLR2004
                return None
            detail = exc.read().decode(errors="replace")
            msg = f"{method} {endpoint}: HTTP {exc.code} {detail}"
            raise GarageAdminError(msg) from exc
        return json.loads(raw) if raw else None


def init_storage(admin: GarageAdmin, layout: StorageLayout) -> list[str]:
    """Bring the node into the state the shop needs; returns what was changed."""
    changes: list[str] = []
    if _ensure_node_role(admin):
        changes.append("Knoten in das Layout aufgenommen")
    if _ensure_key(admin, layout):
        changes.append(f"Zugangsschlüssel {layout.access_key_id} angelegt")
    for alias in (layout.private_bucket, layout.public_bucket):
        bucket_id, created = _ensure_bucket(admin, alias)
        if created:
            changes.append(f"Bucket {alias} angelegt")
        admin.call(
            "POST",
            "AllowBucketKey",
            body={
                "bucketId": bucket_id,
                "accessKeyId": layout.access_key_id,
                "permissions": {"read": True, "write": True, "owner": True},
            },
        )
        if alias == layout.public_bucket and _ensure_website(admin, bucket_id):
            changes.append(f"Öffentlicher Lesezugriff für {alias} eingeschaltet")
    return changes


def _ensure_node_role(admin: GarageAdmin) -> bool:
    status = admin.call("GET", "GetClusterStatus")
    nodes = status.get("nodes", [])
    if not nodes:
        msg = "the cluster status lists no node"
        raise GarageAdminError(msg)
    node = next((n for n in nodes if n.get("isUp")), nodes[0])
    if node.get("role"):
        return False
    layout = admin.call("GET", "GetClusterLayout")
    staged = layout.get("stagedRoleChanges") or []
    if not any(change.get("id") == node["id"] for change in staged):
        admin.call(
            "POST",
            "UpdateClusterLayout",
            body={
                "roles": [
                    {
                        "id": node["id"],
                        "zone": NODE_ZONE,
                        "capacity": NODE_CAPACITY_BYTES,
                        "tags": [],
                    }
                ]
            },
        )
    admin.call("POST", "ApplyClusterLayout", body={"version": int(layout["version"]) + 1})
    return True


def _ensure_key(admin: GarageAdmin, layout: StorageLayout) -> bool:
    if admin.call("GET", "GetKeyInfo", query={"id": layout.access_key_id}, missing_ok=True):
        return False
    admin.call(
        "POST",
        "ImportKey",
        body={
            "accessKeyId": layout.access_key_id,
            "secretAccessKey": layout.secret_access_key,
            "name": KEY_NAME,
        },
    )
    return True


def _ensure_bucket(admin: GarageAdmin, alias: str) -> tuple[str, bool]:
    info = admin.call("GET", "GetBucketInfo", query={"globalAlias": alias}, missing_ok=True)
    if info:
        return str(info["id"]), False
    created = admin.call("POST", "CreateBucket", body={"globalAlias": alias})
    return str(created["id"]), True


def _ensure_website(admin: GarageAdmin, bucket_id: str) -> bool:
    info = admin.call("GET", "GetBucketInfo", query={"id": bucket_id})
    if info.get("websiteAccess"):
        return False
    admin.call(
        "POST",
        "UpdateBucket",
        query={"id": bucket_id},
        body={
            "websiteAccess": {"enabled": True, "indexDocument": "index.html", "errorDocument": None}
        },
    )
    return True
