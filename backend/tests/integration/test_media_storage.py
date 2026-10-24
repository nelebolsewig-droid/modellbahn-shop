"""The S3 adapter and the storage set-up against a real Garage node (as in the stack).

``TEST_GARAGE_IMAGE`` overrides the image; the node runs with the configuration of the
stack (infra/garage/garage.toml), started through testcontainers.
"""

import asyncio
import os
import secrets
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

import pytest
from testcontainers.core.container import DockerContainer
from typer.testing import CliRunner

from modellbahn.cli import app
from modellbahn.modules.media.domain.model import original_key
from modellbahn.modules.media.infrastructure.garage import (
    GarageAdmin,
    StorageLayout,
    init_storage,
)
from modellbahn.modules.media.infrastructure.storage import (
    PUBLIC_CACHE_CONTROL,
    OriginalTooLargeError,
    S3MediaStorage,
)
from tests.support import BACKEND_ROOT

DEFAULT_GARAGE_IMAGE = "dxflrs/garage:v2.1.0"
ADMIN_TOKEN = secrets.token_urlsafe(24)
LAYOUT = StorageLayout(
    access_key_id="GK" + secrets.token_hex(12),
    secret_access_key=secrets.token_hex(32),
    private_bucket="mb-media-private",
    public_bucket="mb-media-public",
)


@dataclass(frozen=True)
class Garage:
    s3_url: str
    web_url: str
    admin_url: str
    admin: GarageAdmin


@pytest.fixture(scope="module")
def garage() -> Iterator[Garage]:
    config = BACKEND_ROOT.parent / "infra" / "garage" / "garage.toml"
    container = (
        DockerContainer(os.environ.get("TEST_GARAGE_IMAGE", DEFAULT_GARAGE_IMAGE))
        .with_env("GARAGE_RPC_SECRET", secrets.token_hex(32))
        .with_env("GARAGE_ADMIN_TOKEN", ADMIN_TOKEN)
        .with_volume_mapping(str(config), "/etc/garage.toml", "ro")
        .with_exposed_ports(3900, 3902, 3903)
    )
    with container:
        host = container.get_container_host_ip()

        def url(port: int) -> str:
            return f"http://{host}:{container.get_exposed_port(port)}"

        admin = GarageAdmin(url(3903), ADMIN_TOKEN)
        admin.wait_until_reachable(timeout_seconds=30)
        yield Garage(s3_url=url(3900), web_url=url(3902), admin_url=url(3903), admin=admin)


@pytest.fixture(scope="module")
def storage(garage: Garage) -> S3MediaStorage:
    assert init_storage(garage.admin, LAYOUT)
    return S3MediaStorage(
        endpoint_url=garage.s3_url,
        public_endpoint_url=garage.s3_url,
        region="garage",
        access_key_id=LAYOUT.access_key_id,
        secret_access_key=LAYOUT.secret_access_key,
        private_bucket=LAYOUT.private_bucket,
        public_bucket=LAYOUT.public_bucket,
    )


def put(url: str, data: bytes, content_type: str) -> int:
    request = urllib.request.Request(  # noqa: S310
        url, data=data, method="PUT", headers={"Content-Type": content_type}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return exc.code


def public_get(garage: Garage, key: str) -> tuple[int, dict[str, str]]:
    request = urllib.request.Request(  # noqa: S310
        f"{garage.web_url}/{key}",
        headers={"Host": f"{LAYOUT.public_bucket}.web.garage.localhost"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            return int(response.status), {k.lower(): v for k, v in response.headers.items()}
    except urllib.error.HTTPError as exc:
        return exc.code, {}


def test_init_storage_is_idempotent(garage: Garage, storage: S3MediaStorage) -> None:
    assert init_storage(garage.admin, LAYOUT) == []


async def test_signed_upload_accepts_exactly_the_announced_file(storage: S3MediaStorage) -> None:
    asset_id = uuid4()
    key = original_key(asset_id)
    data = b"\xff\xd8\xff" + secrets.token_bytes(2048)
    url = storage.presign_original_upload(
        key, content_type="image/jpeg", content_length=len(data), expires_in=timedelta(minutes=15)
    )
    assert "X-Amz-SignedHeaders=content-length%3Bcontent-type%3Bhost" in url
    assert await asyncio.to_thread(put, url, data, "image/png") == 403
    assert await asyncio.to_thread(put, url, data + b"!", "image/jpeg") == 403
    assert await storage.original_size(key) is None
    assert await asyncio.to_thread(put, url, data, "image/jpeg") == 200
    assert await storage.original_size(key) == len(data)
    assert await storage.read_original(key, max_bytes=len(data)) == data
    with pytest.raises(OriginalTooLargeError):
        await storage.read_original(key, max_bytes=len(data) - 1)


async def test_signed_upload_expires(storage: S3MediaStorage) -> None:
    url = storage.presign_original_upload(
        original_key(uuid4()),
        content_type="image/jpeg",
        content_length=3,
        expires_in=timedelta(seconds=1),
    )
    await asyncio.sleep(2)
    # Garage answers an expired signature with 400 (AccessDenied for a wrong one).
    assert await asyncio.to_thread(put, url, b"abc", "image/jpeg") in {400, 403}


async def test_renditions_are_public_and_immutable(garage: Garage, storage: S3MediaStorage) -> None:
    asset_id = uuid4()
    key = f"{asset_id}/thumb-1a2b3c4d.webp"
    await storage.publish_rendition(key, b"RIFF....WEBP", content_type="image/webp")
    status, headers = await asyncio.to_thread(public_get, garage, key)
    assert status == 200
    assert headers["content-type"] == "image/webp"
    assert headers["cache-control"] == PUBLIC_CACHE_CONTROL
    # The private bucket has no website access.
    request = urllib.request.Request(  # noqa: S310
        f"{garage.web_url}/{original_key(asset_id)}",
        headers={"Host": f"{LAYOUT.private_bucket}.web.garage.localhost"},
    )
    with pytest.raises(urllib.error.HTTPError):
        await asyncio.to_thread(urllib.request.urlopen, request, timeout=10)


async def test_delete_files_removes_everything_of_one_asset(
    garage: Garage, storage: S3MediaStorage
) -> None:
    asset_id, other_id = uuid4(), uuid4()
    for owner in (asset_id, other_id):
        url = storage.presign_original_upload(
            original_key(owner),
            content_type="image/jpeg",
            content_length=3,
            expires_in=timedelta(minutes=1),
        )
        assert await asyncio.to_thread(put, url, b"abc", "image/jpeg") == 200
        for name in ("thumb", "md"):
            await storage.publish_rendition(
                f"{owner}/{name}-00000000.webp", b"x", content_type="image/webp"
            )
    await storage.delete_files(asset_id)
    await storage.delete_files(asset_id)
    assert await storage.original_size(original_key(asset_id)) is None
    assert (await asyncio.to_thread(public_get, garage, f"{asset_id}/md-00000000.webp"))[0] == 404
    assert await storage.original_size(original_key(other_id)) == 3
    assert (await asyncio.to_thread(public_get, garage, f"{other_id}/md-00000000.webp"))[0] == 200
    await storage.delete_renditions([f"{other_id}/md-00000000.webp"])
    deadline = time.monotonic() + 5
    while (await asyncio.to_thread(public_get, garage, f"{other_id}/md-00000000.webp"))[0] != 404:
        assert time.monotonic() < deadline
        await asyncio.sleep(0.1)


def test_cli_sets_up_the_storage(garage: Garage, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    admin_url = garage.admin_url
    monkeypatch.delenv("GARAGE_ADMIN_TOKEN", raising=False)
    refused = runner.invoke(app, ["init-storage", "--admin-url", admin_url])
    assert refused.exit_code == 1
    assert "Kein Admin-Token" in refused.output
    env = {"GARAGE_ADMIN_TOKEN": ADMIN_TOKEN, "GARAGE_ADMIN_URL": admin_url}
    first = runner.invoke(app, ["init-storage"], env=env)
    assert first.exit_code == 0, first.output
    assert "Zugangsschlüssel" in first.output
    again = runner.invoke(app, ["init-storage"], env=env)
    assert again.output.strip() == "Objektspeicher war schon eingerichtet."
    wrong = runner.invoke(
        app, ["init-storage", "--wait-seconds", "0"], env={**env, "GARAGE_ADMIN_TOKEN": "falsch"}
    )
    assert wrong.exit_code == 1
    assert "nicht eingerichtet" in wrong.output
