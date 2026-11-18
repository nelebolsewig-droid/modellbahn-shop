"""What a sliced print file says about its plate (ADR 0037).

The slicer (Chitubox at adp-Modelle) writes, before the layers, a header with the resin
the plate takes, its weight, the slicer's price and the print time. Only that head of
the file is read, never the layers: the browser sends the first :data:`HEAD_BYTES` of a
file that can be hundreds of megabytes.

Formats:

* **CTB, encrypted** (magic ``0x12FD0107``, Chitubox 1.9 and later, e.g. for the
  Saturn 4 Ultra): the settings block is AES-256-CBC. Its key is the one the free
  UVtools publishes for the format; it opens the files the workshop itself made.
* **CTB / CBDDLP, plain** (magic ``0x12FD0086`` and ``0x12FD0019``): little-endian
  header, the amounts in the print parameters it points at.
* **GOO** (Elegoo, version ``V3.0``): big-endian header after two RGB565 previews.

Pure, so it is tested with built bytes and no printer.
"""

import base64
import struct
from dataclasses import dataclass
from typing import Final

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

HEAD_BYTES: Final = 512 * 1024
"""What of a file is read: enough for the GOO previews and the CTB parameters, and as
Base64 still below the 1 MB the proxy lets through to the API."""

MAGIC_CTB: Final = 0x12FD0086
MAGIC_CBDDLP: Final = 0x12FD0019
MAGIC_CTB_ENCRYPTED: Final = 0x12FD0107

_UVTOOLS: Final = b"UVtools"
_CTB_KEY: Final = "hQ36XB6yTk+zO02ysyiowt8yC1buK+nbLWyfY40EXoU="
_CTB_IV: Final = "Wld+ampndVJecmVjYH5cWQ=="

_NAME_MAX: Final = 256
_VOLUME_MAX_ML: Final = 100_000

_GOO_VERSION: Final = b"V3.0"
_GOO_MAGIC: Final = bytes((0x07, 0x00, 0x00, 0x00, 0x44, 0x4C, 0x50, 0x00))
# Version, magic, five names, three levels; two previews with their delimiters; then
# layer count, resolution and mirror flags up to the first float.
_GOO_NAMES: Final = struct.Struct(">4s8s32s24s24s32s32s32sHHH")
_GOO_PREVIEWS: Final = 116 * 116 * 2 + 2 + 290 * 290 * 2 + 2
_GOO_PLATE: Final = struct.Struct(
    ">IHH??"  # layers, resolution, mirror
    "fffff"  # display width/height, machine z, layer height, exposure
    "B"  # delay mode
    "fffffff"  # light-off delay and six wait times
    "fI"  # bottom exposure, bottom layers
    "ffffffff"  # lift and retract, first stage
    "ffffffff"  # lift and retract, second stage
    "HH?"  # light PWM, per-layer settings
    "Ifff"  # print time, volume, grams, cost
)


# The decrypted settings: what is read of them, at their byte offsets.
_CTB_SETTINGS: Final = struct.Struct(
    "<36x f"  # layer height at 36
    "24x I"  # layer count at 64
    "8x I"  # print time in seconds at 76
    "24x fff"  # millilitres, grams, cost at 104
    "44x II"  # machine name offset and size at 160
)


class UnreadableSliceFileError(ValueError):
    """Not a sliced file this reader knows, or cut off before the amounts."""


@dataclass(frozen=True, slots=True)
class SliceFile:
    """One plate as the slicer computed it."""

    format: str
    """``ctb`` or ``goo``."""
    machine: str
    """The printer profile, e.g. ``ELEGOO Saturn 4 Ultra 16K``; empty if the file has none."""
    volume_ml: float
    grams: float
    cost: float
    """The slicer's own price, in the currency set there: shown, never computed with."""
    print_seconds: int
    layer_height_mm: float
    layer_count: int


def read_slice_file(head: bytes) -> SliceFile:
    """The plate from the first bytes of a sliced file."""
    if head[:4] == _GOO_VERSION and head[4:12] == _GOO_MAGIC:
        return _goo(head)
    magic = int.from_bytes(head[:4], "little")
    if magic == MAGIC_CTB_ENCRYPTED:
        return _ctb_encrypted(head)
    if magic in (MAGIC_CTB, MAGIC_CBDDLP):
        return _ctb_plain(head)
    raise UnreadableSliceFileError("not a sliced CTB or GOO file")


def _checked(file: SliceFile) -> SliceFile:
    if not 0 < file.volume_ml < _VOLUME_MAX_ML or file.print_seconds < 0 or file.layer_count <= 0:
        raise UnreadableSliceFileError("the file has no plausible amounts")
    return file


def _slice(head: bytes, offset: int, size: int) -> bytes:
    if offset < 0 or size <= 0 or offset + size > len(head):
        raise UnreadableSliceFileError("the file is cut off before its settings")
    return head[offset : offset + size]


def _text(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("utf-8", "replace").strip()


def _uvtools(secret: str) -> bytes:
    raw = base64.b64decode(secret)
    return bytes(byte ^ _UVTOOLS[i % len(_UVTOOLS)] for i, byte in enumerate(raw))


def _ctb_encrypted(head: bytes) -> SliceFile:
    settings_size, settings_offset = struct.unpack_from("<II", head, 4)
    block = _slice(head, settings_offset, settings_size)
    if settings_size % 16:
        raise UnreadableSliceFileError("the settings block is not whole")
    decryptor = Cipher(algorithms.AES(_uvtools(_CTB_KEY)), modes.CBC(_uvtools(_CTB_IV))).decryptor()
    settings = decryptor.update(block) + decryptor.finalize()
    if len(settings) < _CTB_SETTINGS.size:
        raise UnreadableSliceFileError("the settings block is too short")
    fields = _CTB_SETTINGS.unpack_from(settings)
    layer_height, layer_count, print_seconds = fields[0], fields[1], fields[2]
    volume, grams, cost = fields[3:6]
    name_offset, name_size = fields[6:8]
    fits = 0 < name_size <= _NAME_MAX and name_offset + name_size <= len(head)
    machine = _text(head[name_offset : name_offset + name_size]) if fits else ""
    return _checked(
        SliceFile(
            format="ctb",
            machine=machine,
            volume_ml=volume,
            grams=grams,
            cost=cost,
            print_seconds=print_seconds,
            layer_height_mm=layer_height,
            layer_count=layer_count,
        )
    )


def _ctb_plain(head: bytes) -> SliceFile:
    header = _slice(head, 0, 112)
    layer_height = struct.unpack_from("<f", header, 32)[0]
    layer_count, _, print_seconds = struct.unpack_from("<III", header, 68)
    params_offset, params_size = struct.unpack_from("<II", header, 84)
    params = _slice(head, params_offset, max(params_size, 32))
    volume, grams, cost = struct.unpack_from("<fff", params, 20)
    return _checked(
        SliceFile(
            format="ctb",
            machine="",
            volume_ml=volume,
            grams=grams,
            cost=cost,
            print_seconds=print_seconds,
            layer_height_mm=layer_height,
            layer_count=layer_count,
        )
    )


def _goo(head: bytes) -> SliceFile:
    names = _GOO_NAMES.unpack(_slice(head, 0, _GOO_NAMES.size))
    plate = _GOO_PLATE.unpack(_slice(head, _GOO_NAMES.size + _GOO_PREVIEWS, _GOO_PLATE.size))
    layer_count, layer_height = plate[0], plate[8]
    print_seconds, volume, grams, cost = plate[-4:]
    return _checked(
        SliceFile(
            format="goo",
            machine=_text(names[5]),
            volume_ml=volume,
            grams=grams,
            cost=cost,
            print_seconds=print_seconds,
            layer_height_mm=layer_height,
            layer_count=layer_count,
        )
    )
