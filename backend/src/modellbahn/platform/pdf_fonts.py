"""The shop's typeface for PDFs drawn with reportlab: Geist, as on the website.

Geist (SIL Open Font License, see ``fonts/OFL.txt``) is embedded in each PDF. Registering
fonts with reportlab is process-wide, so it happens once.
"""

from importlib.resources import files
from io import BytesIO
from typing import Final

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

SANS: Final = "Geist"
SANS_MEDIUM: Final = "Geist-Medium"
MONO: Final = "GeistMono-Medium"
_FONT_FILES: Final = {
    SANS: "Geist-Regular.ttf",
    SANS_MEDIUM: "Geist-Medium.ttf",
    MONO: "GeistMono-Medium.ttf",
}

_registered = False


def register_fonts() -> None:
    """Make the shop's fonts known to reportlab; calling it again does nothing."""
    global _registered  # noqa: PLW0603 - registering with reportlab is process-wide
    if _registered:
        return
    folder = files("modellbahn.platform") / "fonts"
    for name, filename in _FONT_FILES.items():
        with (folder / filename).open("rb") as font_file:
            pdfmetrics.registerFont(TTFont(name, BytesIO(font_file.read())))
    _registered = True
