"""Administrative commands: ``python -m modellbahn.cli --help``."""

import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from functools import partial
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from pydantic import EmailStr, TypeAdapter, ValidationError

from modellbahn.modules.identity.application.services import IdentityService
from modellbahn.modules.identity.domain.errors import (
    AccountAlreadyExistsError,
    AccountNotFoundError,
    InvalidDisplayNameError,
    PasswordPolicyViolationError,
    PasswordRule,
)
from modellbahn.modules.identity.domain.model import (
    DISPLAY_NAME_MAX_LENGTH,
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    StaffRole,
)
from modellbahn.modules.identity.infrastructure.mapping import start_mappers
from modellbahn.modules.identity.infrastructure.repositories import SqlIdentityUnitOfWork
from modellbahn.modules.media.infrastructure.garage import (
    GarageAdmin,
    GarageAdminError,
    StorageLayout,
    init_storage,
)
from modellbahn.platform.clock import SystemClock
from modellbahn.platform.config import Settings
from modellbahn.platform.db import create_engine, create_session_factory
from modellbahn.platform.security import Argon2PasswordHasher

app = typer.Typer(
    help="Verwaltungsbefehle des Modellbahn-Shops.",
    no_args_is_help=True,
    add_completion=False,
)

_PASSWORD_RULES = {
    PasswordRule.TOO_SHORT: f"Das Passwort muss mindestens {PASSWORD_MIN_LENGTH} Zeichen haben.",
    PasswordRule.TOO_LONG: f"Das Passwort darf höchstens {PASSWORD_MAX_LENGTH} Zeichen haben.",
    PasswordRule.EQUALS_EMAIL: "Das Passwort darf nicht die E-Mail-Adresse sein.",
}


@app.command("create-staff")
def create_staff(
    email: Annotated[str, typer.Option(help="E-Mail-Adresse für die Anmeldung.")],
    name: Annotated[str, typer.Option(help="Anzeigename, z. B. Vor- und Nachname.")],
    role: Annotated[StaffRole, typer.Option(help="Rolle im Admin-Bereich.")],
    password_stdin: Annotated[
        bool,
        typer.Option(
            "--password-stdin", help="Passwort von der Standardeingabe lesen statt abzufragen."
        ),
    ] = False,
) -> None:
    """Mitarbeiterkonto anlegen."""
    try:
        address = TypeAdapter(EmailStr).validate_python(email)
    except ValidationError:
        _fail(f"Keine gültige E-Mail-Adresse: {email}")
    password = _read_password_stdin() if password_stdin else _prompt_password()
    try:
        asyncio.run(
            _with_service(
                Settings(),
                lambda service: service.create_staff(
                    email=address, display_name=name, role=role, password=password
                ),
            )
        )
    except PasswordPolicyViolationError as exc:
        _fail(_PASSWORD_RULES[exc.rule])
    except InvalidDisplayNameError:
        _fail(f"Der Name muss 1 bis {DISPLAY_NAME_MAX_LENGTH} Zeichen haben (ohne Steuerzeichen).")
    except AccountAlreadyExistsError:
        _fail(f"Es gibt schon ein Mitarbeiterkonto mit der Adresse {address}.")
    typer.echo(f"Mitarbeiterkonto angelegt: {address} ({role.value})")


@app.command("unlock-staff")
def unlock_staff(
    email: Annotated[str, typer.Option(help="E-Mail-Adresse des gesperrten Mitarbeiterkontos.")],
) -> None:
    """Sperre eines Mitarbeiterkontos nach zu vielen Fehlversuchen aufheben.

    Kunden heben eine Sperre selbst auf, indem sie ihr Passwort zurücksetzen. Für
    Mitarbeiterkonten gibt es das nicht, weil sonst jeder, der die Adresse kennt,
    den Admin-Zugang dauerhaft sperren könnte.
    """
    try:
        asyncio.run(_with_service(Settings(), lambda service: service.unlock_staff(email=email)))
    except AccountNotFoundError:
        _fail(f"Es gibt kein aktives Mitarbeiterkonto mit der Adresse {email}.")
    typer.echo(f"Sperre aufgehoben: {email}")


@app.command("init-storage")
def init_storage_command(
    admin_url: Annotated[
        str, typer.Option(envvar="GARAGE_ADMIN_URL", help="Adresse der Admin-API von Garage.")
    ] = "http://localhost:3903",
    admin_token: Annotated[
        str,
        typer.Option(envvar="GARAGE_ADMIN_TOKEN", help="Token der Admin-API.", show_default=False),
    ] = "",
    wait_seconds: Annotated[
        float, typer.Option(help="So lange auf den Speicher warten, der gerade startet.")
    ] = 60.0,
) -> None:
    """Objektspeicher (Garage) einrichten: Layout, Zugangsschlüssel, Buckets.

    Prüft jeden Schritt vorher und ändert nur, was fehlt; mehrfach ausführen schadet nicht.
    Schlüssel und Bucket-Namen kommen aus den MB_S3_*- und MB_MEDIA_*-Einstellungen.
    """
    if not admin_token:
        _fail("Kein Admin-Token: GARAGE_ADMIN_TOKEN setzen oder --admin-token angeben.")
    settings = Settings()
    admin = GarageAdmin(admin_url, admin_token)
    layout = StorageLayout(
        access_key_id=settings.s3_access_key_id,
        secret_access_key=settings.s3_secret_access_key.get_secret_value(),
        private_bucket=settings.media_private_bucket,
        public_bucket=settings.media_public_bucket,
    )
    try:
        admin.wait_until_reachable(timeout_seconds=wait_seconds)
        changes = init_storage(admin, layout)
    except (OSError, GarageAdminError) as exc:
        _fail(f"Objektspeicher nicht eingerichtet: {exc}")
    for change in changes:
        typer.echo(change)
    typer.echo(
        "Objektspeicher ist eingerichtet." if changes else "Objektspeicher war schon eingerichtet."
    )


@app.command("export-openapi")
def export_openapi(
    output: Annotated[
        Path, typer.Option(help="Zieldatei, relativ zum aktuellen Verzeichnis.")
    ] = Path("../frontend/openapi.json"),
) -> None:
    """OpenAPI-Schema der API als JSON schreiben (für den Client des Frontends)."""
    # Imported here: building the app is only needed for this command.
    from modellbahn.main import create_app  # noqa: PLC0415

    document = create_app(Settings()).openapi()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    typer.echo(f"OpenAPI-Schema geschrieben: {output}")


async def _with_service(
    settings: Settings, action: Callable[[IdentityService], Awaitable[object]]
) -> None:
    """Run ``action`` with an identity service on its own engine, then close the engine."""
    engine = create_engine(settings.database_url)
    start_mappers()
    service = IdentityService(
        uow_factory=partial(SqlIdentityUnitOfWork, create_session_factory(engine)),
        hasher=Argon2PasswordHasher.from_settings(settings),
        clock=SystemClock(),
    )
    try:
        await action(service)
    finally:
        await engine.dispose()


def _read_password_stdin() -> str:
    password = sys.stdin.read().removesuffix("\n").removesuffix("\r")
    if not password:
        _fail("Auf der Standardeingabe kam kein Passwort an.")
    return password


def _prompt_password() -> str:
    password: str = typer.prompt(
        "Passwort", hide_input=True, confirmation_prompt="Passwort wiederholen"
    )
    return password


def _fail(message: str) -> NoReturn:
    typer.echo(f"Fehler: {message}", err=True)
    raise typer.Exit(code=1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
