"""The CLI and the worker process."""

import asyncio
import json
import os
import signal
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from modellbahn.cli import app as cli
from modellbahn.modules.identity.application.services import IdentityService, UnitOfWorkFactory
from modellbahn.modules.identity.domain.model import AccountKind, StaffRole
from modellbahn.platform.config import Settings
from modellbahn.platform.mail import InMemoryMailer
from modellbahn.worker import run_worker
from tests.support import BACKEND_ROOT, eventually, token_from

PASSWORD = "Gleis 7 und Weiche 3"


@pytest.fixture
def cli_env(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MB_DATABASE_URL", settings.database_url)
    monkeypatch.setenv("MB_ENVIRONMENT", "test")
    monkeypatch.setenv("MB_ARGON2_TIME_COST", "1")
    monkeypatch.setenv("MB_ARGON2_MEMORY_COST", "8")
    monkeypatch.setenv("MB_ARGON2_PARALLELISM", "1")


def create_staff(*args: str, password: str = PASSWORD) -> tuple[int, str]:
    result = CliRunner().invoke(
        cli,
        ["create-staff", "--email", "chefin@example.com", "--name", "Chefin", *args],
        input=f"{password}\n",
    )
    return result.exit_code, result.output


@pytest.mark.usefixtures("cli_env")
class TestCreateStaff:
    async def test_creates_an_account_that_can_log_in(
        self, identity: IdentityService, uow_factory: UnitOfWorkFactory
    ) -> None:
        exit_code, output = await asyncio.to_thread(
            create_staff, "--role", "owner", "--password-stdin"
        )
        assert exit_code == 0, output
        assert "Mitarbeiterkonto angelegt: chefin@example.com (owner)" in output

        started = await identity.login(
            kind=AccountKind.STAFF, email="chefin@example.com", password=PASSWORD, user_agent=None
        )
        assert started.account.role is StaffRole.OWNER

        exit_code, output = await asyncio.to_thread(
            create_staff, "--role", "staff", "--password-stdin"
        )
        assert exit_code == 1
        assert "Es gibt schon ein Mitarbeiterkonto" in output

    async def test_prompts_twice_without_password_stdin(self) -> None:
        runner = CliRunner()
        result = await asyncio.to_thread(
            runner.invoke,
            cli,
            ["create-staff", "--email", "lager@example.com", "--name", "Lager", "--role", "packer"],
            input=f"{PASSWORD}\n{PASSWORD}\n",
        )
        assert result.exit_code == 0, result.output
        assert "Passwort wiederholen" in result.output

    @pytest.mark.parametrize(
        ("args", "password", "message"),
        [
            (["--role", "owner", "--password-stdin"], "kurz", "mindestens 10 Zeichen"),
            (["--role", "owner", "--password-stdin"], "x" * 300, "höchstens 256 Zeichen"),
            (["--role", "owner", "--password-stdin"], "chefin@example.com", "nicht die E-Mail"),
            (["--role", "owner", "--password-stdin"], "", "kein Passwort"),
        ],
    )
    async def test_rejects_bad_passwords(
        self, args: list[str], password: str, message: str
    ) -> None:
        exit_code, output = await asyncio.to_thread(create_staff, *args, password=password)
        assert exit_code == 1
        assert message in output

    async def test_rejects_bad_input(self) -> None:
        runner = CliRunner()
        bad_email = await asyncio.to_thread(
            runner.invoke,
            cli,
            ["create-staff", "--email", "kein-mail", "--name", "X", "--role", "owner"],
        )
        assert bad_email.exit_code == 1
        assert "Keine gültige E-Mail-Adresse" in bad_email.output

        bad_name = await asyncio.to_thread(
            runner.invoke,
            cli,
            [
                "create-staff",
                "--email",
                "a@example.com",
                "--name",
                " ",
                "--role",
                "owner",
                "--password-stdin",
            ],
            input=f"{PASSWORD}\n",
        )
        assert bad_name.exit_code == 1
        assert "Der Name muss 1 bis 80 Zeichen haben" in bad_name.output

        bad_role = await asyncio.to_thread(
            runner.invoke,
            cli,
            ["create-staff", "--email", "a@example.com", "--name", "X", "--role", "boss"],
        )
        assert bad_role.exit_code == 2


def test_export_openapi_writes_sorted_json(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "openapi.json"
    result = CliRunner().invoke(cli, ["export-openapi", "--output", str(target)])
    assert result.exit_code == 0, result.output
    content = target.read_text(encoding="utf-8")
    assert content.endswith("}\n")
    document = json.loads(content)
    assert content == json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    assert document["info"]["title"] == "Modellbahn-Shop API"


async def test_worker_sends_the_verification_mail(
    settings: Settings, identity: IdentityService
) -> None:
    mailer = InMemoryMailer()
    stop = asyncio.Event()
    worker = asyncio.create_task(run_worker(settings, stop, mailer=mailer))
    try:
        await identity.register_customer(
            email="kunde@example.com", password=PASSWORD, display_name="Erika"
        )

        async def mail() -> str | None:
            return token_from(mailer.sent[0]) if mailer.sent else None

        token = await eventually(mail)
        started = await identity.verify_email(token=token, user_agent=None)
        assert started.account.email_verified
    finally:
        stop.set()
        async with asyncio.timeout(5):
            await worker


async def test_worker_process_stops_gracefully_on_sigterm(settings: Settings) -> None:
    env = {
        **os.environ,
        "MB_DATABASE_URL": settings.database_url,
        "MB_ENVIRONMENT": "production",
        "MB_LOG_LEVEL": "INFO",
    }
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "modellbahn.worker",
        cwd=BACKEND_ROOT,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert process.stdout is not None
    try:
        async with asyncio.timeout(20):
            while b"outbox.dispatcher.started" not in await process.stdout.readline():
                pass
        process.send_signal(signal.SIGTERM)
        async with asyncio.timeout(10):
            remaining = await process.stdout.read()
            exit_code = await process.wait()
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()

    assert exit_code == 0
    lines = [json.loads(line) for line in remaining.decode().splitlines() if line.startswith("{")]
    events = [line["event"] for line in lines]
    assert "worker.stopping" in events
    assert "outbox.dispatcher.stopped" in events
