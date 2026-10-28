"""Application settings, read from ``MB_*`` environment variables."""

import re
from email.utils import parseaddr
from enum import StrEnum
from typing import Literal, Self

from argon2 import DEFAULT_MEMORY_COST, DEFAULT_PARALLELISM, DEFAULT_TIME_COST
from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from modellbahn.platform.imprint import Imprint

type LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

_ASYNC_DRIVER_PREFIX = "postgresql+asyncpg://"
_DEFAULT_SHOP_NAME = "Modellbahn-Shop"
# German VAT identification number: DE and nine digits (§ 27a UStG).
_VAT_ID = re.compile(r"^DE[0-9]{9}$")
# The development key of .env.example, which init-storage imports into the local storage.
_DEVELOPMENT_S3_ACCESS_KEY_ID = "GKba9ff40c8a82b4ef09ebaf72"
_DEVELOPMENT_S3_SECRET_ACCESS_KEY = (
    "7f38e28c0803bd1400af0bea7463f260950bc644c40e3bdc2e19579fde50dbbf"  # noqa: S105
)


class Environment(StrEnum):
    """Where the process runs; production enables the strict safety checks."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """All runtime configuration of the API, the worker and the CLI.

    Every field maps to an environment variable with the ``MB_`` prefix, e.g.
    ``database_url`` is read from ``MB_DATABASE_URL``. The defaults suit a local
    development setup; production must provide real values.
    """

    model_config = SettingsConfigDict(env_prefix="MB_", frozen=True, extra="ignore")

    # Left out of repr(): the URL contains the database password.
    database_url: str = Field(
        default="postgresql+asyncpg://modellbahn:modellbahn@localhost:5432/modellbahn",
        repr=False,
    )
    environment: Environment = Environment.DEVELOPMENT
    public_base_url: str = "http://localhost:3000"
    cookie_secure: bool = True

    smtp_host: str = "localhost"
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_from: str = f"{_DEFAULT_SHOP_NAME} <noreply@modellbahn.local>"
    smtp_starttls: bool = False
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None

    argon2_time_cost: int = Field(default=DEFAULT_TIME_COST, ge=1)
    argon2_memory_cost: int = Field(default=DEFAULT_MEMORY_COST, ge=8)
    argon2_parallelism: int = Field(default=DEFAULT_PARALLELISM, ge=1)

    outbox_poll_seconds: float = Field(default=5.0, gt=0)
    outbox_max_attempts: int = Field(default=10, ge=1, le=32767)

    # Requests per client address to login, registration, verification and reset
    # routes within the window; 0 switches the limit off.
    auth_rate_limit: int = Field(default=30, ge=0)
    auth_rate_window_seconds: float = Field(default=600.0, gt=0)
    # The same for checkouts and payments together; 0 switches the limit off.
    checkout_rate_limit: int = Field(default=30, ge=0)
    checkout_rate_window_seconds: float = Field(default=600.0, gt=0)

    # Object storage (S3 API). The defaults reach the storage service of docker-compose.yml
    # from the host, with the development key of .env.example.
    s3_endpoint_url: str = "http://localhost:3900"
    # Where browsers send uploads; presigned URLs are signed for this host.
    s3_public_endpoint_url: str = "http://localhost:3900"
    s3_region: str = "garage"
    s3_access_key_id: str = _DEVELOPMENT_S3_ACCESS_KEY_ID
    s3_secret_access_key: SecretStr = SecretStr(_DEVELOPMENT_S3_SECRET_ACCESS_KEY)
    # Originals stay private; the rendered image sizes are public.
    media_private_bucket: str = "mb-media-private"
    media_public_bucket: str = "mb-media-public"
    # Prefix of public image URLs. Relative by default: Caddy serves /medien on the site.
    media_public_base_url: str = "/medien"

    log_level: LogLevel = "INFO"

    # The provider details of the imprint and the e-mail footer (§ 5 DDG). Personal data
    # of the owner, so they live in the environment, never in the code.
    imprint_company: str = ""
    imprint_owner: str = ""
    imprint_street: str = ""
    imprint_postal_code: str = ""
    imprint_city: str = ""
    imprint_country: str = "Deutschland"
    imprint_phone: str = ""
    imprint_email: str = ""
    imprint_vat_id: str = ""

    fair_news_rate_limit: int = Field(default=10, ge=0)
    fair_news_rate_window_seconds: float = Field(default=600.0, gt=0)

    @field_validator("database_url")
    @classmethod
    def _require_asyncpg_driver(cls, value: str) -> str:
        if not value.startswith(_ASYNC_DRIVER_PREFIX):
            msg = f"must start with {_ASYNC_DRIVER_PREFIX!r}"
            raise ValueError(msg)
        return value

    @field_validator("public_base_url")
    @classmethod
    def _normalise_public_base_url(cls, value: str) -> str:
        # Links in e-mails are built by appending a path, so keep no trailing slash.
        return str(AnyHttpUrl(value)).rstrip("/")

    @field_validator("s3_endpoint_url", "s3_public_endpoint_url")
    @classmethod
    def _normalise_endpoint(cls, value: str) -> str:
        return str(AnyHttpUrl(value)).rstrip("/")

    @field_validator("media_public_base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        # Image URLs are built by appending "/" and the storage key.
        return value.rstrip("/")

    @field_validator("smtp_from")
    @classmethod
    def _require_sender_address(cls, value: str) -> str:
        if "@" not in parseaddr(value)[1]:
            msg = "must contain an e-mail address, e.g. 'Shop <noreply@example.com>'"
            raise ValueError(msg)
        return value

    @field_validator("imprint_vat_id")
    @classmethod
    def _check_vat_id(cls, value: str) -> str:
        cleaned = value.replace(" ", "").upper()
        if cleaned and not _VAT_ID.fullmatch(cleaned):
            msg = "must be DE followed by nine digits, e.g. DE123456789"
            raise ValueError(msg)
        return cleaned

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_case_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _refuse_insecure_production(self) -> Self:
        if self.environment is not Environment.PRODUCTION:
            return self
        if not self.cookie_secure:
            msg = "MB_COOKIE_SECURE=false is not allowed in production"
            raise ValueError(msg)
        if self.s3_access_key_id == _DEVELOPMENT_S3_ACCESS_KEY_ID:
            msg = "the development storage key of .env.example is not allowed in production"
            raise ValueError(msg)
        if not self.imprint.is_complete:
            msg = "the shop needs its imprint in production: set the MB_IMPRINT_* variables"
            raise ValueError(msg)
        return self

    @property
    def is_production(self) -> bool:
        """True when running with ``MB_ENVIRONMENT=production``."""
        return self.environment is Environment.PRODUCTION

    @property
    def shop_name(self) -> str:
        """Display name of the shop, taken from the sender of outgoing e-mails."""
        return parseaddr(self.smtp_from)[0] or _DEFAULT_SHOP_NAME

    @property
    def imprint(self) -> Imprint:
        """The provider details as the imprint, the API and the e-mails show them."""
        return Imprint(
            shop_name=self.shop_name,
            company=self.imprint_company.strip(),
            owner=self.imprint_owner.strip(),
            street=self.imprint_street.strip(),
            postal_code=self.imprint_postal_code.strip(),
            city=self.imprint_city.strip(),
            country=self.imprint_country.strip(),
            phone=self.imprint_phone.strip(),
            email=self.imprint_email.strip(),
            vat_id=self.imprint_vat_id,
        )
