"""PDF pages as pictures for the Brother apps: one per page, 300 dpi, black and white."""

from io import BytesIO

from PIL import Image

from modellbahn.modules.inventory.application.ports import LabelSheet
from modellbahn.modules.inventory.infrastructure.labels import ReportLabLabelRenderer
from modellbahn.platform.pdf_images import pdf_to_pngs
from tests.unit.test_inventory_labels import IMPRINT, LOCATION, UNIT


def test_one_picture_per_label_at_its_true_size() -> None:
    pdf = ReportLabLabelRenderer(maker=IMPRINT.maker_lines()).render(
        [UNIT, LOCATION], sheet=LabelSheet.QL_62X29, skip=0
    )
    pictures = [Image.open(BytesIO(png)) for png in pdf_to_pngs(pdf)]
    assert len(pictures) == 2
    for picture in pictures:
        assert picture.format == "PNG"
        assert picture.size == (733, 343)  # 62 x 29 mm at 300 dpi
        assert picture.mode == "1"
        assert round(picture.info["dpi"][0]) == 300
        # Something is printed, and most of the label stays white.
        histogram = picture.convert("L").histogram()
        assert 0 < histogram[0] < histogram[255]
