"""The manufacturer on the labels of units (EU GPSR): taken from the imprint, fitted to the
space right of the workshop's barcode."""

from dataclasses import replace

from reportlab.lib.units import mm

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
UNIT = Label(
    caption="Einheit",
    code_text="J4WZ XRT2 S2",
    code128="J4WZXRT2S2",
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
    def test_only_units_carry_the_manufacturer(self) -> None:
        plain = ReportLabLabelRenderer()
        with_maker = ReportLabLabelRenderer(maker=IMPRINT.maker_lines())
        for sheet in LabelSheet:
            unit_plain = plain.render([UNIT], sheet=sheet, skip=0)
            unit_maker = with_maker.render([UNIT], sheet=sheet, skip=0)
            assert unit_maker.startswith(b"%PDF")
            assert len(unit_maker) > len(unit_plain)
            location_plain = plain.render([LOCATION], sheet=sheet, skip=0)
            location_maker = with_maker.render([LOCATION], sheet=sheet, skip=0)
            assert len(location_maker) == len(location_plain)
