"""Logging configuration: what an error log line may and may not contain."""

import json
import logging
from collections.abc import Iterator

import pytest
import structlog

from modellbahn.platform.config import Environment, Settings
from modellbahn.platform.logging import configure_logging

SECRET = "Geheim-Marker-4711"


@pytest.fixture
def restore_logging() -> Iterator[None]:
    yield
    configure_logging(environment=Environment.TEST, level="WARNING")


def fail_with_secret_locals(password: str) -> None:
    session_token = f"token-{password}"
    msg = f"database unavailable (session {len(session_token)} characters)"
    raise RuntimeError(msg)


@pytest.mark.usefixtures("restore_logging")
@pytest.mark.parametrize("environment", [Environment.PRODUCTION, Environment.DEVELOPMENT])
def test_exception_logs_leave_out_local_variables(
    environment: Environment, capsys: pytest.CaptureFixture[str]
) -> None:
    # The handler writes to the stderr that is current when logging is configured.
    configure_logging(environment=environment, level="INFO")
    try:
        fail_with_secret_locals(SECRET)
    except RuntimeError:
        structlog.get_logger("test").exception("request.failed")

    output = capsys.readouterr().err
    assert "request.failed" in output
    assert "database unavailable" in output
    assert "fail_with_secret_locals" in output
    assert SECRET not in output


@pytest.mark.usefixtures("restore_logging")
def test_production_writes_one_json_object_per_line(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(environment=Environment.PRODUCTION, level="INFO")
    try:
        fail_with_secret_locals(SECRET)
    except RuntimeError:
        structlog.get_logger("test").exception("request.failed", path="/x")
    logging.getLogger("uvicorn.error").info("plain stdlib record")

    lines = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    assert [line["event"] for line in lines] == ["request.failed", "plain stdlib record"]
    (exception,) = lines[0]["exception"]
    assert exception["exc_type"] == "RuntimeError"
    assert all("locals" not in frame for frame in exception["frames"])


def test_settings_repr_hides_the_database_password() -> None:
    settings = Settings(database_url=f"postgresql+asyncpg://shop:{SECRET}@db:5432/shop")
    assert SECRET not in repr(settings)
    assert SECRET not in str(settings)
