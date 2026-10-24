"""The object storage over the S3 API (Garage in the stack, any S3 service in principle).

boto3 is synchronous, so every call that talks to the storage runs in a worker
thread; the client is thread-safe. Signing an upload URL is local computation.
"""

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING, Final, Self
from uuid import UUID

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from modellbahn.modules.media.domain.model import original_key
from modellbahn.platform.config import Settings

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client

# Rendered sizes never change under their key (it contains a content hash).
PUBLIC_CACHE_CONTROL: Final = "public, max-age=31536000, immutable"
# DeleteObjects takes at most 1000 keys per request.
_DELETE_BATCH: Final = 1000


class OriginalTooLargeError(Exception):
    """The stored original is larger than the caller is willing to read."""


class S3MediaStorage:
    """:class:`~modellbahn.modules.media.application.ports.MediaStorage` over the S3 API.

    Two clients share the credentials: one talks to the storage directly (inside the
    stack, ``http://storage:3900``), the other only signs upload URLs for the address
    browsers use (the site itself, where Caddy forwards the PUT to the storage).
    """

    def __init__(
        self,
        *,
        endpoint_url: str,
        public_endpoint_url: str,
        region: str,
        access_key_id: str,
        secret_access_key: str,
        private_bucket: str,
        public_bucket: str,
    ) -> None:
        config = Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            retries={"mode": "standard", "max_attempts": 3},
            connect_timeout=5,
            read_timeout=30,
            # Checksums only where S3 requires them: signed upload URLs must not demand
            # a checksum header the browser does not send.
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        )
        self._client: S3Client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
            config=config,
        )
        self._signer: S3Client = boto3.client(
            "s3",
            endpoint_url=public_endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
            config=config,
        )
        self._private = private_bucket
        self._public = public_bucket

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        return cls(
            endpoint_url=settings.s3_endpoint_url,
            public_endpoint_url=settings.s3_public_endpoint_url,
            region=settings.s3_region,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key.get_secret_value(),
            private_bucket=settings.media_private_bucket,
            public_bucket=settings.media_public_bucket,
        )

    def presign_original_upload(
        self, key: str, *, content_type: str, content_length: int, expires_in: timedelta
    ) -> str:
        return self._signer.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self._private,
                "Key": key,
                "ContentType": content_type,
                "ContentLength": content_length,
            },
            ExpiresIn=int(expires_in.total_seconds()),
            HttpMethod="PUT",
        )

    async def original_size(self, key: str) -> int | None:
        try:
            head = await asyncio.to_thread(self._client.head_object, Bucket=self._private, Key=key)
        except ClientError as exc:
            if _is_not_found(exc):
                return None
            raise
        return head["ContentLength"]

    async def read_original(self, key: str, *, max_bytes: int) -> bytes:
        return await asyncio.to_thread(self._read, self._private, key, max_bytes)

    def _read(self, bucket: str, key: str, max_bytes: int) -> bytes:
        response = self._client.get_object(Bucket=bucket, Key=key)
        body = response["Body"]
        try:
            if response["ContentLength"] > max_bytes:
                msg = f"{key} has {response['ContentLength']} bytes, more than {max_bytes}"
                raise OriginalTooLargeError(msg)
            return body.read()
        finally:
            body.close()

    async def publish_rendition(self, key: str, data: bytes, *, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._public,
            Key=key,
            Body=data,
            ContentType=content_type,
            CacheControl=PUBLIC_CACHE_CONTROL,
        )

    async def delete_renditions(self, keys: list[str]) -> None:
        await asyncio.to_thread(self._delete, self._public, keys)

    async def delete_files(self, asset_id: UUID) -> None:
        await asyncio.to_thread(self._delete_prefix, self._private, original_key(asset_id))
        await asyncio.to_thread(self._delete_prefix, self._public, f"{asset_id}/")

    def _delete_prefix(self, bucket: str, prefix: str) -> None:
        paginator = self._client.get_paginator("list_objects_v2")
        keys = [
            item["Key"]
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix)
            for item in page.get("Contents", [])
        ]
        self._delete(bucket, keys)

    def _delete(self, bucket: str, keys: list[str]) -> None:
        for start in range(0, len(keys), _DELETE_BATCH):
            batch = keys[start : start + _DELETE_BATCH]
            self._client.delete_objects(
                Bucket=bucket,
                Delete={"Objects": [{"Key": key} for key in batch], "Quiet": True},
            )


def _is_not_found(error: ClientError) -> bool:
    code = str(error.response.get("Error", {}).get("Code", ""))
    return code in {"404", "NoSuchKey", "NotFound"}
