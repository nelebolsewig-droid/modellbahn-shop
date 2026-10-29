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

from modellbahn.modules.catalog.api.seed_file import SeedFile
from modellbahn.modules.catalog.application.importing import (
    CatalogSeed,
    ImportReport,
    SeedError,
    import_catalog,
)
from modellbahn.modules.catalog.application.services import CatalogService
from modellbahn.modules.catalog.infrastructure.mapping import (
    start_mappers as start_catalog_mappers,
)
from modellbahn.modules.catalog.infrastructure.repositories import catalog_uow_factory
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
from modellbahn.modules.media.infrastructure.mapping import (
    start_mappers as start_media_mappers,
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


@app.command("import-catalog")
def import_catalog_command(
    path: Annotated[Path, typer.Argument(help="JSON-Datei, z. B. seed/startbestand.json.")],
) -> None:
    """Startbestand des Katalogs einspielen: Kategorien und Produkte als Entwürfe.

    Wiederholbar: Was es schon gibt (gleicher Name, gleiche Adresse), bleibt unberührt.
    """
    try:
        seed = SeedFile.read(path).to_seed()
    except FileNotFoundError:
        _fail(f"Datei nicht gefunden: {path}")
    except ValidationError as exc:
        _fail(f"Die Datei passt nicht zum Format:\n{exc}")
    try:
        report = asyncio.run(_import_catalog(Settings(), seed))
    except SeedError as exc:
        _fail(f"Nichts eingespielt. {exc}")
    for path_name in report.categories:
        typer.echo(f"Kategorie angelegt: {path_name}")
    for name in report.products:
        typer.echo(f"Entwurf angelegt:   {name}")
    for name in report.skipped:
        typer.echo(f"Schon vorhanden:    {name}")
    for name, note in report.notes:
        typer.echo(f"Hinweis zu {name}: {note}")
    typer.echo(
        f"{len(report.products)} Produkte und {len(report.categories)} Kategorien angelegt, "
        f"{len(report.skipped)} übersprungen. Alle neuen Produkte sind Entwürfe."
    )


async def _import_catalog(settings: Settings, seed: CatalogSeed) -> ImportReport:
    engine = create_engine(settings.database_url)
    start_media_mappers()
    start_catalog_mappers()
    service = CatalogService(
        uow_factory=catalog_uow_factory(
            create_session_factory(engine), public_base_url=settings.media_public_base_url
        ),
        clock=SystemClock(),
    )
    try:
        return await import_catalog(service, seed)
    finally:
        await engine.dispose()


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
