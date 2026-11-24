#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["websockets>=13"]
# ///
"""Drucker-Brücke: meldet, was die Resin-Drucker tun, an die Fertigung im Stellwerk (ADR 0047).

Läuft auf einem Rechner im Werkstatt-WLAN (Mac oder Raspberry Pi). Die Elegoo-Drucker
(Saturn 3 Ultra, Saturn 4 Ultra …) sprechen im Netz SDCP: Suche per UDP an Port 3000,
Zustand per WebSocket an Port 3030. Die Brücke hält zu jedem Drucker eine Verbindung,
fragt alle paar Sekunden den Zustand ab und schickt alle 15 Sekunden die Lage an
``/api/v1/webhooks/printer-bridge``. Der Server startet, beendet oder verwirft daraus die
Platten; doppelt melden schadet nicht.

Die Brücke baut nur Verbindungen nach außen auf: Am Router muss nichts freigegeben werden.

Aufruf (``uv`` installiert die Abhängigkeit selbst)::

    uv run drucker_bruecke.py suchen                 # Drucker im WLAN finden
    uv run drucker_bruecke.py probe  drucker.toml    # nur anzeigen, nichts senden
    uv run drucker_bruecke.py        drucker.toml    # laufen lassen

``drucker.toml``::

    server = "https://www.adp-modelle.de"
    schluessel = "…"            # MB_PRINTER_BRIDGE_TOKEN auf dem Server

    [drucker]                   # Code im Stellwerk = IP-Adresse im WLAN
    D01 = "192.168.178.41"
    D02 = "192.168.178.42"
"""

import asyncio
import contextlib
import json
import logging
import socket
import sys
import time
import tomllib
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import websockets

DISCOVERY_PORT: Final = 3000
WEBSOCKET_PORT: Final = 3030
POLL_SECONDS: Final = 5
SEND_SECONDS: Final = 15
STALE_SECONDS: Final = 60
"""Older news from a printer is not sent: it may be off or out of the WLAN."""
RECONNECT_SECONDS: Final = 20

# SDCP V3: PrintInfo.Status
_IDLE: Final = 0
_STOPPED: Final = 8
_COMPLETE: Final = frozenset({9, 16})

log = logging.getLogger("drucker-bruecke")


@dataclass
class Printer:
    code: str
    ip: str
    mainboard_id: str = ""
    info: dict[str, Any] = field(default_factory=dict)
    seen_at: float = 0.0

    def report(self) -> dict[str, Any] | None:
        """What the server needs to know, or ``None`` while nothing fresh is known."""
        if not self.info or time.monotonic() - self.seen_at > STALE_SECONDS:
            return None
        status = int(self.info.get("Status", 0) or 0)
        if status in _COMPLETE:
            state = "finished"
        elif status == _STOPPED:
            state = "stopped"
        elif status == _IDLE:
            state = "idle"
        else:
            state = "printing"
        current, total = _seconds(self.info.get("CurrentTicks"), self.info.get("TotalTicks"))
        error = int(self.info.get("ErrorNumber", 0) or 0)
        return {
            "code": self.code,
            "state": state,
            "task_id": str(self.info.get("TaskId") or ""),
            "slice_file": str(self.info.get("Filename") or ""),
            "elapsed_seconds": current,
            "remaining_seconds": max(total - current, 0) if total else None,
            "error": f"Fehler {error} am Drucker" if error else "",
        }


def _seconds(current: Any, total: Any) -> tuple[int, int | None]:
    """Time gone and the whole print in seconds.

    SDCP gives milliseconds, some firmware seconds. A resin print takes less than two
    days: a larger total can only be milliseconds.
    """
    if not isinstance(total, int | float) or total <= 0:
        total = None
    if not isinstance(current, int | float) or current < 0:
        current = 0
    factor = 1000 if total and total > 2 * 24 * 3600 else 1
    return int(current / factor), (int(total / factor) if total else None)


# --- Suchen ------------------------------------------------------------------------------


def discover(timeout: float = 3.0, target: str = "255.255.255.255") -> list[dict[str, Any]]:
    """Every SDCP printer that answers ``M99999`` on the network (or at ``target``)."""
    found: dict[str, dict[str, Any]] = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.5)
        sock.sendto(b"M99999", (target, DISCOVERY_PORT))
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                data, (ip, _) = sock.recvfrom(8192)
            except TimeoutError:
                continue
            with contextlib.suppress(ValueError):
                found[ip] = json.loads(data).get("Data", {}) | {"ip": ip}
    return list(found.values())


# --- Verbindung zum Drucker --------------------------------------------------------------


async def watch(printer: Printer) -> None:
    """Keep a connection to one printer and its latest PrintInfo, forever."""
    url = f"ws://{printer.ip}:{WEBSOCKET_PORT}/websocket"
    while True:
        try:
            if not printer.mainboard_id:
                answers = await asyncio.to_thread(discover, 2.0, printer.ip)
                printer.mainboard_id = str(answers[0].get("MainboardID", "")) if answers else ""
            async with websockets.connect(url, open_timeout=10, ping_interval=None) as ws:
                log.info("%s verbunden (%s)", printer.code, printer.ip)
                poller = asyncio.create_task(_poll(ws, printer))
                try:
                    async for message in ws:
                        _take(printer, message)
                finally:
                    poller.cancel()
        except (OSError, websockets.WebSocketException, TimeoutError) as error:
            log.warning("%s nicht erreichbar (%s): %s", printer.code, printer.ip, error)
        await asyncio.sleep(RECONNECT_SECONDS)


async def _poll(ws: Any, printer: Printer) -> None:
    while True:
        await ws.send(
            json.dumps(
                {
                    "Id": "",
                    "Data": {
                        "Cmd": 0,
                        "Data": {},
                        "RequestID": uuid.uuid4().hex,
                        "MainboardID": printer.mainboard_id,
                        "TimeStamp": int(time.time()),
                        "From": 0,
                    },
                    "Topic": f"sdcp/request/{printer.mainboard_id}",
                }
            )
        )
        await asyncio.sleep(POLL_SECONDS)


def _take(printer: Printer, message: str | bytes) -> None:
    try:
        data = json.loads(message)
    except ValueError:
        return  # "pong" and the like
    status = data.get("Status") if isinstance(data, dict) else None
    if isinstance(status, dict) and isinstance(status.get("PrintInfo"), dict):
        printer.info = status["PrintInfo"]
        printer.seen_at = time.monotonic()
        printer.mainboard_id = printer.mainboard_id or str(data.get("MainboardID", ""))


# --- Melden ans Stellwerk ----------------------------------------------------------------


def send(server: str, key: str, reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    request = urllib.request.Request(  # noqa: S310 - the URL comes from the owner's config
        f"{server.rstrip('/')}/api/v1/webhooks/printer-bridge",
        data=json.dumps({"printers": reports}).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "drucker-bruecke",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310
        results: list[dict[str, Any]] = json.loads(response.read())["results"]
        return results


async def run(config: dict[str, Any], *, dry: bool) -> None:
    printers = [Printer(code=code, ip=ip) for code, ip in config["drucker"].items()]
    for printer in printers:
        asyncio.create_task(watch(printer))  # noqa: RUF006 - they live as long as the loop
    last: dict[str, str] = {}
    while True:
        await asyncio.sleep(SEND_SECONDS)
        reports = [r for p in printers if (r := p.report()) is not None]
        if not reports:
            continue
        if dry:
            for report in reports:
                log.info("%s", report)
            continue
        try:
            results = await asyncio.to_thread(send, config["server"], config["schluessel"], reports)
        except (urllib.error.URLError, OSError, ValueError, KeyError) as error:
            log.warning("Stellwerk nicht erreichbar: %s", error)
            continue
        for result in results:
            text = f"{result['outcome']} {result.get('job_number') or ''}".strip()
            if last.get(result["code"]) != text:
                log.info("%s: %s", result["code"], _german(result))
                last[result["code"]] = text


def _german(result: dict[str, Any]) -> str:
    number = result.get("job_number")
    return {
        "started": f"Druck {number} gestartet",
        "printing": f"Druck {number} läuft",
        "printed": f"Druck {number} fertig, ab in die Nachbearbeitung",
        "failed": f"Druck {number} abgebrochen",
        "already_booked": f"Druck {number} ist schon erfasst",
        "unmatched": "Druck ohne passende Platte und ohne Teilenummer im Dateinamen",
        "unknown_printer": "Code nicht im Stellwerk angelegt",
        "not_in_service": "Drucker steht im Stellwerk nicht auf „in Betrieb“",
        "nothing": "frei",
    }.get(result["outcome"], result["outcome"])


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    if argv[:1] == ["suchen"]:
        printers = discover()
        if not printers:
            print("Kein Drucker gefunden. Gleiches WLAN? Drucker an?")  # noqa: T201
        for p in printers:
            print(f"{p['ip']:<16} {p.get('Name', '')}  {p.get('MachineName', '')}")  # noqa: T201
        return 0
    dry = argv[:1] == ["probe"]
    rest = argv[1:] if dry else argv
    path = Path(rest[0] if rest else "drucker.toml")
    config = tomllib.loads(path.read_text(encoding="utf-8"))
    if not config.get("drucker"):
        print(f"In {path} stehen keine Drucker unter [drucker].")  # noqa: T201
        return 1
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run(config, dry=dry))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
