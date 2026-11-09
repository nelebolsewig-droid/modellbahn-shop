"""PDF pages as PNG images, for label printers whose apps print images, not PDFs.

Brother's apps (iPrint&Label, P-touch Editor) take a picture per label. Each page becomes
one PNG at the printer's 300 dpi in pure black and white, as a thermal printer prints:
nothing grey is left to be dithered, and the bars of barcodes keep sharp edges. The PNG
carries its resolution, so the app prints it at its true size.
"""

from io import BytesIO
from typing import Final

import pypdfium2 as pdfium
from PIL import Image

PRINTER_DPI: Final = 300
# Grey up to here prints black: the dark edge of smoothed letters (and any grey a PDF
# brings); the light edge drops away.
_BLACK_BELOW: Final = 170
_POINTS_PER_INCH: Final = 72


def pdf_to_pngs(pdf: bytes, *, dpi: int = PRINTER_DPI) -> list[bytes]:
    """One PNG per page of ``pdf``."""
    document = pdfium.PdfDocument(pdf)
    try:
        pages: list[bytes] = []
        for index in range(len(document)):
            page = document[index]
            try:
                bitmap = page.render(
                    scale=dpi / _POINTS_PER_INCH, grayscale=True, no_smoothpath=True
                )
                grey: Image.Image = bitmap.to_pil()
            finally:
                page.close()
            image = grey.point(lambda value: 0 if value < _BLACK_BELOW else 255).convert("1")
            buffer = BytesIO()
            image.save(buffer, format="PNG", dpi=(dpi, dpi), optimize=True)
            pages.append(buffer.getvalue())
        return pages
    finally:
        document.close()
