"""The labels of models: the EAN-13 and what the model is, no code of a single piece; the
manufacturer (EU GPSR) taken from the imprint and fitted to the space across the bottom."""

from dataclasses import replace

import pypdfium2 as pdfium
from reportlab.lib.units import mm

from modellbahn.modules.inventory.application.labels import document_name, file_name
from modellbahn.modules.inventory.application.ports import Label, LabelSheet
from modellbahn.modules.inventory.infrastructure.labels import (
    ReportLabLabelRenderer,
    maker_block,
)
from modellbahn.platform.imprint import Imprint

IMPRINT = Imprint(
    shop_name="adp-Modelle",
    company="adp-Modelle",
    owner="Johann-Leon Diesterhaupt",
    street="Glambecker Straße 2",
    postal_code="17235",
    city="Neustrelitz",
    country="Deutschland",
    phone="",
    email="info@adp-modelle.de",
    vat_id="",
)
MODEL = Label(
    caption="Modell",
    code_text="",
    code128="",
    ean13="4262441230064",
    title="Stellwerk Altenau",
    detail="H0 · bemalt",
    reference="MB-000006-H0-B",
)
LOCATION = Label(
    caption="Lagerplatz",
    code_text="R01-F02",
    code128="R01-F02",
    title="Fach",
    detail="Fach",
    reference="L / R01 / F02",
)


class TestMakerLines:
    def test_name_address_and_email_from_the_imprint(self) -> None:
        assert IMPRINT.maker_lines() == (
            "adp-Modelle",
            "Johann-Leon Diesterhaupt",
            "Glambecker Straße 2",
            "DE-17235 Neustrelitz",
            "info@adp-modelle.de",
        )

    def test_abroad_the_country_is_named(self) -> None:
        vienna = replace(IMPRINT, postal_code="1010", city="Wien", country="Österreich")
        assert vienna.maker_lines()[3:5] == ("1010 Wien", "Österreich")

    def test_nothing_without_a_complete_imprint(self) -> None:
        assert replace(IMPRINT, street="").maker_lines() == ()


class TestMakerBlock:
    def test_wraps_to_the_width_and_fits_the_height(self) -> None:
        size, lines = maker_block(IMPRINT.maker_lines(), width=17.5 * mm, height=14 * mm, size=5)
        assert lines[:3] == ["adp-Modelle", "Johann-Leon", "Diesterhaupt"]
        assert "info@adp-modelle.de" in lines
        assert len(lines) * size * 1.18 <= 14 * mm
        assert size > 4

    def test_gets_smaller_but_never_drops_a_line(self) -> None:
        maker = IMPRINT.maker_lines()
        size, lines = maker_block(maker, width=17.5 * mm, height=6 * mm, size=5)
        assert size == 3.75
        assert " ".join(lines) == " ".join(maker)


class TestRenderer:
    def test_the_price_is_printed_where_there_is_one(self) -> None:
        renderer = ReportLabLabelRenderer()
        for sheet in LabelSheet:
            without = renderer.render([MODEL], sheet=sheet, skip=0)
            with_price = renderer.render(
                [replace(MODEL, price="79,90\u00a0€")], sheet=sheet, skip=0
            )
            assert len(with_price) > len(without)

    def test_only_models_carry_the_manufacturer(self) -> None:
        plain = ReportLabLabelRenderer()
        with_maker = ReportLabLabelRenderer(maker=IMPRINT.maker_lines())
        for sheet in LabelSheet:
            model_plain = plain.render([MODEL], sheet=sheet, skip=0)
            model_maker = with_maker.render([MODEL], sheet=sheet, skip=0)
            assert model_maker.startswith(b"%PDF")
            assert len(model_maker) > len(model_plain)
            location_plain = plain.render([LOCATION], sheet=sheet, skip=0)
            location_maker = with_maker.render([LOCATION], sheet=sheet, skip=0)
            assert len(location_maker) == len(location_plain)

    def test_a_models_label_names_the_model_never_a_piece(self) -> None:
        renderer = ReportLabLabelRenderer(maker=IMPRINT.maker_lines())
        # Even a label that still knew a piece's code prints none.
        old = replace(MODEL, code_text="J4WZ XRT2 S2", code128="J4WZXRT2S2")
        for sheet in LabelSheet:
            text = _text(renderer.render([old], sheet=sheet, skip=0))
            assert "MODELL" in text
            assert "Stellwerk Altenau" in text
            assert "MB-000006-H0-B" in text
            assert "info@adp-modelle.de" in text
            assert "J4WZ" not in text


def _text(pdf: bytes) -> str:
    document = pdfium.PdfDocument(pdf)
    try:
        return "".join(page.get_textpage().get_text_range() for page in document)
    finally:
        document.close()


class TestFileNames:
    def test_a_variant_title_becomes_a_plain_file_name(self) -> None:
        assert (
            file_name("IFA ADK 70 Autokran · H0 · Fertigmodell, Gelb")
            == "IFA ADK 70 Autokran H0 Fertigmodell Gelb"
        )
        assert file_name('Kran 1:87 / "Spezial" <neu>?') == "Kran 1 87 Spezial neu"
        assert file_name("  ") == "Etiketten"
        assert len(file_name("A" * 300)) == 100

    def test_a_print_is_named_after_what_its_labels_are_for(self) -> None:
        same = ["IFA ADK 70 Autokran H0 Fertigmodell Gelb"] * 3
        assert document_name(same) == "IFA ADK 70 Autokran H0 Fertigmodell Gelb"
        assert document_name([*same, "Platz R01-F01"]) == (
            "IFA ADK 70 Autokran H0 Fertigmodell Gelb und 1 weitere"
        )
        assert document_name([]) == "Etiketten"
