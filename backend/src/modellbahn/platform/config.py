"""Application settings, read from ``MB_*`` environment variables."""

from email.utils import parseaddr
from enum import StrEnum
from typing import Literal, Self

from argon2 import DEFAULT_MEMORY_COST, DEFAULT_PARALLELISM, DEFAULT_TIME_COST
from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

type LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

_ASYNC_DRIVER_PREFIX = "postgresql+asyncpg://"
_DEFAULT_SHOP_NAME = "Modellbahn-Shop"


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

    log_level: LogLevel = "INFO"

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

    @field_validator("smtp_from")
    @classmethod
    def _require_sender_address(cls, value: str) -> str:
        if "@" not in parseaddr(value)[1]:
            msg = "must contain an e-mail address, e.g. 'Shop <noreply@example.com>'"
            raise ValueError(msg)
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_case_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _refuse_insecure_production(self) -> Self:
        if self.environment is Environment.PRODUCTION and not self.cookie_secure:
            msg = "MB_COOKIE_SECURE=false is not allowed in production"
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
