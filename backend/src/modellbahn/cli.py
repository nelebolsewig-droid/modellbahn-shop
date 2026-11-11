"""Administrative commands: ``python -m modellbahn.cli --help``."""

import asyncio
import json
import re
import sys
from collections.abc import Awaitable, Callable
from functools import partial
from pathlib import Path
from typing import Annotated, Final, NoReturn

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
    LastOwnerError,
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
from modellbahn.modules.sales.application.ports import LabelRequest
from modellbahn.modules.sales.domain.errors import CarrierRejectedError, CarrierUnavailableError
from modellbahn.modules.sales.domain.labels import LabelAddress, ShippingProduct
from modellbahn.modules.sales.infrastructure.carriers import DhlCarrier, dhl_carrier, shipper_of
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


@app.command("list-staff")
def list_staff() -> None:
    """Aktive Mitarbeiterkonten anzeigen: Adresse, Rolle, Name."""
    members = asyncio.run(_with_service(Settings(), lambda service: service.staff_members()))
    if not members:
        typer.echo("Es gibt kein aktives Mitarbeiterkonto.")
        return
    for member in members:
        role = member.role.value if member.role is not None else "-"
        typer.echo(f"{member.email}  {role}  {member.display_name}")


@app.command("delete-staff")
def delete_staff(
    email: Annotated[str, typer.Option(help="E-Mail-Adresse des Mitarbeiterkontos.")],
    yes: Annotated[bool, typer.Option("--yes", help="Ohne Rückfrage löschen.")] = False,
) -> None:
    """Mitarbeiterkonto löschen.

    Anmeldungen enden sofort; Adresse und Name verschwinden, auch aus dem Verlauf der
    Ereignisse. Bestellungen und Buchungen, an denen das Konto beteiligt war, bleiben.
    Das letzte Inhaberkonto lässt sich nicht löschen.
    """
    if not yes:
        typer.confirm(f"Mitarbeiterkonto {email} löschen?", abort=True)
    try:
        asyncio.run(_with_service(Settings(), lambda service: service.delete_staff(email=email)))
    except AccountNotFoundError:
        _fail(f"Es gibt kein aktives Mitarbeiterkonto mit der Adresse {email}.")
    except LastOwnerError:
        _fail(f"{email} ist das letzte Inhaberkonto. Erst ein anderes anlegen, dann löschen.")
    typer.echo(f"Mitarbeiterkonto gelöscht: {email}")


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


# Two made-up recipients DHL accepts: one at home (DHL Paket), one abroad (International).
_DHL_CHECK_SHIPMENTS: Final = (
    (
        "Inland",
        ShippingProduct.PARCEL,
        LabelAddress(
            name="Max Mustermann",
            street="Charles-de-Gaulle-Straße",
            house_number="20",
            postal_code="53113",
            city="Bonn",
            country="DEU",
        ),
    ),
    (
        "EU-Ausland",
        ShippingProduct.PARCEL_INTERNATIONAL,
        LabelAddress(
            name="Erika Musterfrau",
            street="Stephansplatz",
            house_number="1",
            postal_code="1010",
            city="Wien",
            country="AUT",
        ),
    ),
)
_MEDIA_BOX: Final = re.compile(
    rb"/MediaBox\s*\[\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*\]"
)
_POINTS_PER_MM: Final = 72 / 25.4


@app.command("dhl-check")
def dhl_check(
    sandbox: Annotated[
        bool,
        typer.Option(
            "--sandbox",
            help="In DHLs Sandbox als DHLs Testkunde prüfen; braucht nur MB_DHL_API_KEY.",
        ),
    ] = False,
    book: Annotated[
        bool,
        typer.Option(
            "--buchen",
            help="Nur mit --sandbox: zusätzlich ein Testlabel buchen, vermessen und stornieren.",
        ),
    ] = False,
) -> None:
    """DHL-Zugang prüfen, ohne ein Label zu buchen.

    Lässt DHL je eine Probesendung im Inland und ins EU-Ausland prüfen (validate) und
    zeigt DHLs Antwort im Wortlaut. Dabei entsteht kein Label, und es kostet nichts.
    Ohne --sandbox mit dem Geschäftskundenkonto (MB_DHL_USERNAME, MB_DHL_PASSWORD,
    MB_DHL_EKP), auch solange MB_DHL_MODE noch „off“ ist.
    """
    try:
        settings = Settings()
    except ValidationError as exc:
        _fail(f"Die Einstellungen passen nicht:\n{exc}")
    if book and not sandbox:
        _fail("--buchen gibt es nur mit --sandbox; echte Labels bucht nur das Stellwerk.")
    missing = [
        name
        for name, value in (
            ("MB_DHL_API_KEY", settings.dhl_api_key.get_secret_value()),
            ("MB_DHL_USERNAME", "-" if sandbox else settings.dhl_username),
            ("MB_DHL_PASSWORD", "-" if sandbox else settings.dhl_password.get_secret_value()),
            ("MB_DHL_EKP", "-" if sandbox else settings.dhl_ekp),
        )
        if not value
    ]
    if missing:
        _fail(f"Es fehlt: {', '.join(missing)}. Einrichten mit scripts/einrichten.sh.")
    shipper = shipper_of(settings)
    if shipper is None:
        _fail("Das Impressum ist unvollständig (MB_IMPRINT_*); DHL braucht den Absender.")
    carrier = dhl_carrier(settings, sandbox=sandbox)
    where = "Sandbox (DHLs Testkunde)" if sandbox else "Geschäftskundenkonto"
    typer.echo(f"DHL-Prüfung, {where}: {carrier.base_url}")
    typer.echo(f"Absender: {shipper.name}, {shipper.postal_code} {shipper.city}")
    if not asyncio.run(_dhl_check(carrier, shipper, book=book)):
        raise typer.Exit(code=1)


async def _dhl_check(carrier: DhlCarrier, shipper: LabelAddress, *, book: bool) -> bool:
    accepted = True
    try:
        for title, product, consignee in _DHL_CHECK_SHIPMENTS:
            request = LabelRequest(
                reference="PRUEFUNG",
                product=product,
                shipper=shipper,
                consignee=consignee,
                weight_g=1000,
            )
            number = carrier.billing_number(product)
            typer.echo("")
            typer.echo(
                f"{title} ({product.value}), Abrechnungsnummer "
                f"…{number[6:10]} {number[10:12]} {number[12:]}"
            )
            answer = await carrier.validate(request)
            verdict = "angenommen" if answer.accepted else "abgelehnt"
            typer.echo(f"  DHL antwortet {answer.status}: {verdict}")
            if answer.reason:
                typer.echo(f"  {answer.reason}")
            typer.echo(json.dumps(answer.body, indent=2, ensure_ascii=False))
            accepted = accepted and answer.accepted
        if book and accepted:
            typer.echo("")
            label = await carrier.book(_dhl_check_request(shipper))
            typer.echo(
                f"Testlabel gebucht: {label.shipment_number}, {len(label.document) // 1024} KB, "
                f"{_page_size(label.document)}, Druckformat {label.print_format}"
            )
            await carrier.cancel(label.shipment_number)
            typer.echo("Testlabel wieder storniert.")
    except CarrierUnavailableError:
        typer.echo("DHL ist nicht erreichbar (Netz oder Störung bei DHL).", err=True)
        return False
    except CarrierRejectedError as exc:
        typer.echo(f"DHL lehnt ab: {exc.reason}", err=True)
        return False
    finally:
        await carrier.aclose()
    typer.echo("")
    typer.echo("DHL nimmt beide Sendungen an." if accepted else "DHL lehnt ab; siehe oben.")
    return accepted


def _dhl_check_request(shipper: LabelAddress) -> LabelRequest:
    _, product, consignee = _DHL_CHECK_SHIPMENTS[0]
    return LabelRequest(
        reference="PRUEFUNG", product=product, shipper=shipper, consignee=consignee, weight_g=1000
    )


def _page_size(document: bytes) -> str:
    match = _MEDIA_BOX.search(document)
    if match is None:
        return "Seitengröße nicht erkannt"
    left, bottom, right, top = (float(value) for value in match.groups())
    width, height = abs(right - left) / _POINTS_PER_MM, abs(top - bottom) / _POINTS_PER_MM
    return f"Seite {width:.0f} x {height:.0f} mm"


@app.command("gallery-colors")
def gallery_colors() -> None:
    """Fotos ihrer Farbe zuordnen, wo der Bildtext sie nennt („Stellwerk Altenau, Rot“).

    Für Fotos, die das Foto-Skript hochgeladen hat, bevor es die Farbe selbst zuordnete:
    Ohne Zuordnung zeigt der Shop bei jeder Farbe das erste Foto. Mehrfach ausführen
    schadet nicht.
    """
    tagged = asyncio.run(_tag_gallery_colors(Settings()))
    for product, color in tagged:
        typer.echo(f"{product}: Foto der Farbe {color} zugeordnet")
    typer.echo(f"{len(tagged)} Fotos zugeordnet." if tagged else "Es gab nichts zuzuordnen.")


async def _tag_gallery_colors(settings: Settings) -> list[tuple[str, str]]:
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
        return await service.tag_colors_from_alt_texts()
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


async def _with_service[T](
    settings: Settings, action: Callable[[IdentityService], Awaitable[T]]
) -> T:
    """Run ``action`` with an identity service on its own engine, then close the engine."""
    engine = create_engine(settings.database_url)
    start_mappers()
    service = IdentityService(
        uow_factory=partial(SqlIdentityUnitOfWork, create_session_factory(engine)),
        hasher=Argon2PasswordHasher.from_settings(settings),
        clock=SystemClock(),
    )
    try:
        return await action(service)
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
