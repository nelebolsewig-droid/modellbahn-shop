"""What the printer bridge reads from a sliced file's name (ADR 0050)."""

import pytest

from modellbahn.modules.manufacturing.application.bridge import (
    file_stem,
    part_number_from,
    parts_on_plate,
    scale_from,
)


@pytest.mark.parametrize(
    ("file", "stem"),
    [
        ("v10c_tür_32.stl_0.040_4.000_2026_11_25_11_01.ctb", "v10c_tür_32"),
        (
            "H6_Zementsilo_Rahmen_mit_Raedern.stl_#17_0.040_4.000_2026_11_25_10_53.ctb",
            "H6_Zementsilo_Rahmen_mit_Raedern",
        ),
        ("/local/Kran_0.050_2.500_2026_11_25_11_01.ctb", "Kran"),
        ("BR_99_23-24_dummy.stl #4.ctb", "BR_99_23-24_dummy"),
        ("Wartburg 353 4x TT.goo", "Wartburg 353 4x TT"),
    ],
)
def test_the_model_is_what_is_left_of_the_name(file: str, stem: str) -> None:
    assert file_stem(file) == stem


def test_number_count_and_scale() -> None:
    assert part_number_from("v10c_tür_32") == "V10C-TUER-32"
    assert parts_on_plate("Wartburg 353 4x TT") == 4
    assert parts_on_plate("Dach X12") == 12
    assert parts_on_plate("Kran") == 1
    assert scale_from("Kran TT", {"H0": "", "TT": ""}) == "TT"
    assert scale_from("Kran", {"H0": "", "TT": ""}) == "H0"
