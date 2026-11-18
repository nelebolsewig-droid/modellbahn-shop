"""Reading the plate from the head of a sliced print file (ADR 0037)."""

import struct

import pytest

from modellbahn.modules.manufacturing.domain.slice_files import (
    MAGIC_CTB,
    UnreadableSliceFileError,
    read_slice_file,
)

# The first 336 bytes of a real plate Nele sliced in Chitubox for the Saturn 4 Ultra
# (BR 99 23-24, 18.11.2026): file header and the encrypted settings block.
SATURN_4_ULTRA_HEAD = bytes.fromhex(
    "0701fd1220010000300000000000000005000000200000006236670f000000000100010000000000"
    "2a00000000000000f22702d09cf80fe9d5982798eacfad2e4d8194ac0fd271f5be83b354be53e544"
    "3d4fccdee27e46fddce403988842b52d2f299a87d62759aa70d66c50c9891a9a490cf56f36db0fd2"
    "a535f6c187504e4d22d7bdad297fc0a5957d0557862873895f36ea8cfdd82e145034fc57ab725224"
    "359e049759e1bfdaae3f5a25a8d915a32ae1504fed88faf2e89161599d30d2a93ec058684f350401"
    "4b353b6aa1ee33b261ebeab3660be5305283a05db3415118cdb8b8bb8c53ddf5adde13b06651f3e0"
    "49585234e895feb5fdebdc5090fc77e21b4d6f54715ad8dbedeb244f89199efda7fe6b63af546ce2"
    "712c1a1f02b0fd07c1d642d5a5771592dae748b54e3049f31e04e5952679e065f43a1876d4fcba20"
    "1fa1819a41a288fdabfa9d4e68d1a331"
)
SATURN_4_ULTRA_NAME_AT = 214_032
SATURN_4_ULTRA_NAME = b"ELEGOO Saturn 4 Ultra 16K"


def _saturn_4_ultra() -> bytes:
    head = bytearray(SATURN_4_ULTRA_NAME_AT + len(SATURN_4_ULTRA_NAME))
    head[: len(SATURN_4_ULTRA_HEAD)] = SATURN_4_ULTRA_HEAD
    head[SATURN_4_ULTRA_NAME_AT:] = SATURN_4_ULTRA_NAME
    return bytes(head)


def test_an_encrypted_ctb_gives_what_chitubox_showed() -> None:
    plate = read_slice_file(_saturn_4_ultra())
    # Chitubox: 62.287 ml, 68.516 g, 2.055 $, 2h44m26s.
    assert plate.format == "ctb"
    assert plate.machine == "ELEGOO Saturn 4 Ultra 16K"
    assert round(plate.volume_ml, 3) == 62.287
    assert round(plate.grams, 3) == 68.516
    assert round(plate.cost, 3) == 2.055
    assert plate.print_seconds == 2 * 3600 + 44 * 60 + 26
    assert round(plate.layer_height_mm, 3) == 0.05
    assert plate.layer_count == 1409


def test_the_machine_name_may_lie_beyond_the_head() -> None:
    plate = read_slice_file(SATURN_4_ULTRA_HEAD)
    assert plate.machine == ""
    assert round(plate.volume_ml, 3) == 62.287


def _plain_ctb(volume: float = 4.2, seconds: int = 3600) -> bytes:
    header = bytearray(112)
    struct.pack_into("<I", header, 0, MAGIC_CTB)
    struct.pack_into("<f", header, 32, 0.05)
    struct.pack_into("<III", header, 68, 800, 0, seconds)
    struct.pack_into("<II", header, 84, 112, 60)
    params = bytearray(60)
    struct.pack_into("<fff", params, 20, volume, volume * 1.1, 0.5)
    return bytes(header + params)


def test_a_plain_ctb_has_its_amounts_in_the_print_parameters() -> None:
    plate = read_slice_file(_plain_ctb())
    assert plate.format == "ctb"
    assert round(plate.volume_ml, 3) == 4.2
    assert plate.print_seconds == 3600
    assert plate.layer_count == 800


def _goo(volume: float = 11.5) -> bytes:
    names = struct.pack(
        ">4s8s32s24s24s32s32s32sHHH",
        b"V3.0",
        bytes((7, 0, 0, 0, 0x44, 0x4C, 0x50, 0)),
        b"CHITUBOX",
        b"2.3",
        b"2026-11-18 22:00:00",
        b"ELEGOO Saturn 3 Ultra",
        b"MSLA",
        b"normal",
        8,
        1,
        0,
    )
    previews = bytes(116 * 116 * 2 + 2 + 290 * 290 * 2 + 2)
    floats = [0.0] * 23
    plate = struct.pack(
        ">IHH??fffffB" + "f" * 8 + "I" + "f" * 16 + "HH?Ifff",
        620, 11520, 5120, False, False,
        218.88, 122.88, 250.0, 0.05, 2.5,
        0,
        *floats[:7],
        30.0, 5,
        *floats[:16],
        255, 255, False,
        5400, volume, volume * 1.1, 0.4,
    )  # fmt: skip
    return names + previews + plate


def test_a_goo_file_reads_behind_its_previews() -> None:
    plate = read_slice_file(_goo())
    assert plate.format == "goo"
    assert plate.machine == "ELEGOO Saturn 3 Ultra"
    assert round(plate.volume_ml, 3) == 11.5
    assert plate.print_seconds == 5400
    assert plate.layer_count == 620
    assert round(plate.layer_height_mm, 3) == 0.05


@pytest.mark.parametrize(
    "head",
    [
        b"",
        b"solid model\nfacet normal 0 0 1",
        SATURN_4_ULTRA_HEAD[:200],
        _plain_ctb()[:120],
        _goo()[:100_000],
        _plain_ctb(volume=0.0),
    ],
    ids=["empty", "stl", "encrypted-cut", "plain-cut", "goo-cut", "no-volume"],
)
def test_what_is_no_sliced_plate_is_refused(head: bytes) -> None:
    with pytest.raises(UnreadableSliceFileError):
        read_slice_file(head)
