"""The photo upload script (scripts/fotos_hochladen.py): reading the overview and the plan.

The requests themselves were tried against the local stack; here only what decides which
photo goes where, in which order.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from tests.support import BACKEND_ROOT

HEADER = (
    "Datei;Modell;Entwurf im Startbestand;Maßstab;Farbe;Ausführung;Zustand;Eignung;"
    "Hauptbild (ja/nein);Bemerkung"
)


@pytest.fixture(scope="module")
def script() -> ModuleType:
    path = BACKEND_ROOT.parent / "scripts" / "fotos_hochladen.py"
    spec = importlib.util.spec_from_file_location("fotos_hochladen", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["fotos_hochladen"] = module  # dataclasses look their module up
    spec.loader.exec_module(module)
    return module


def overview(folder: Path, rows: list[str], files: list[str]) -> Path:
    for name in files:
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(b"\xff\xd8\xff")
    path = folder / "modelle-uebersicht.csv"
    path.write_text("﻿" + "\n".join([HEADER, *rows]) + "\n", encoding="utf-8")
    return path


def test_main_photo_first_then_good_then_usable(script: ModuleType, tmp_path: Path) -> None:
    csv = overview(
        tmp_path,
        [
            "Modelle/b.jpg;IFA ADK 70;IFA ADK 70 Autokran;H0;Gelb;Fertigmodell;gut;brauchbar;nein;",
            "Modelle/c.jpg;IFA ADK 70;IFA ADK 70 Autokran;H0;Gelb;Fertigmodell;gut;gut;nein;",
            "Modelle/a.jpg;IFA ADK 70;IFA ADK 70 Autokran;H0;Gelb;Fertigmodell;gut;gut;ja;",
            "Modelle/d.jpg;IFA ADK 70;IFA ADK 70 Autokran;H0;Gelb;Fertigmodell;gut;"
            "nein, mehrere Modelle;nein;",
            "Modelle/e.jpg;IFA ADK 70;IFA ADK 70 Autokran;H0;Gelb;Fertigmodell;gut;brauchbar;nein;",
        ],
        ["Modelle/a.jpg", "Modelle/b.jpg", "Modelle/c.jpg", "Modelle/d.jpg", "Modelle/e.jpg"],
    )
    photos, missing = script.read_overview(csv)
    plan = script.make_plan(photos, missing, max_photos=3)

    gallery = plan.galleries["IFA ADK 70 Autokran"]
    assert [p.path.name for p in gallery] == ["a.jpg", "c.jpg", "b.jpg"]
    assert gallery[0].alt_text == "IFA ADK 70, Gelb"
    assert plan.over_limit == {"IFA ADK 70 Autokran": 1}
    assert [p.path.name for p in plan.unsuitable] == ["d.jpg"]


def test_new_models_go_by_their_own_name(script: ModuleType, tmp_path: Path) -> None:
    # The photo is found below "Modelle" too, and a listed file that is gone is reported.
    csv = overview(
        tmp_path,
        [
            "x.jpg;IFA W50 LF 16;neu;H0;Rot;Fertigmodell;gut;gut;ja;",
            "y.jpg;IFA W50 LF 16;neu;H0;Rot;Fertigmodell;gut;gut;nein;",
        ],
        ["Modelle/x.jpg"],
    )
    photos, missing = script.read_overview(csv)
    plan = script.make_plan(photos, missing, max_photos=8)

    assert list(plan.galleries) == ["IFA W50 LF 16"]
    assert plan.galleries["IFA W50 LF 16"][0].path == tmp_path / "Modelle" / "x.jpg"
    assert plan.missing_files == ["y.jpg"]


def test_names_match_whatever_the_quotes(script: ModuleType) -> None:
    assert script.normalized("„OSA-AK“ 9T217B") == script.normalized('"osa-ak"  9T217B')
    assert script.normalized("ADK III3 Puma Kran-2") != script.normalized("ADK III3 Puma Kran")


def test_a_list_without_its_columns_is_refused(script: ModuleType, tmp_path: Path) -> None:
    path = tmp_path / "liste.csv"
    path.write_text("Datei;Name\nx.jpg;Kran\n", encoding="utf-8")
    with pytest.raises(script.ListError, match="Modell"):
        script.read_overview(path)


def test_raw_photos_go_up_as_a_jpeg_made_once(script: ModuleType, tmp_path: Path) -> None:
    raw = tmp_path / "IMG_0376.DNG"
    raw.write_bytes(b"raw")
    jpeg = tmp_path / "IMG_0001.jpg"
    jpeg.write_bytes(b"\xff\xd8\xff")
    calls: list[Path] = []

    def convert(source: Path, target: Path) -> None:
        calls.append(source)
        target.write_bytes(b"\xff\xd8\xff converted")

    cache = tmp_path / "cache"
    first = script.file_to_send(raw, convert, cache=cache)
    again = script.file_to_send(raw, convert, cache=cache)

    assert first == again
    assert first.parent == cache
    assert first.suffix == ".jpg"
    assert calls == [raw]  # the second run sends the same bytes, so the server knows them
    assert script.file_to_send(jpeg, convert, cache=cache) == jpeg
    assert list(cache.glob("*.part.jpg")) == []


def test_raw_photos_need_the_mac(script: ModuleType, tmp_path: Path) -> None:
    csv = overview(
        tmp_path,
        [
            "Modelle/a.DNG;GAZ-51;neu;H0;Rot;Fertigmodell;gut;gut;ja;",
            "Modelle/b.jpg;GAZ-51;neu;H0;Rot;Fertigmodell;gut;gut;nein;",
        ],
        ["Modelle/a.DNG", "Modelle/b.jpg"],
    )
    plan = script.make_plan(*script.read_overview(csv), max_photos=8)

    assert script.check_files(plan, can_convert=True) == ([], 1)
    problems, _ = script.check_files(plan, can_convert=False)
    assert [p.split(":")[0] for p in problems] == ["a.DNG"]
    with pytest.raises(script.StellwerkError, match="nur auf dem Mac"):
        script.file_to_send(tmp_path / "Modelle" / "a.DNG", None, cache=tmp_path / "cache")
