"""Every setting must reach the containers: docker-compose.yml lists the variables one by
one, and a missing line silently drops what .env says (ADR 0045, Nachtrag 24.11.)."""

import re
from pathlib import Path

from modellbahn.platform.config import Settings

ROOT = Path(__file__).resolve().parents[3]

IMAGE_DEFAULTS = {
    # Fixed by the image or only for tests; .env never needs to change them.
    "s3_region",
    "media_private_bucket",
    "media_public_bucket",
    "studio_model_path",
    "sumup_api_url",
    "dhl_api_url",
}


def test_every_setting_is_passed_to_the_backend() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    passed = set(re.findall(r"\b(MB_[A-Z0-9_]+)\b", compose))
    wanted = {f"MB_{name.upper()}" for name in Settings.model_fields if name not in IMAGE_DEFAULTS}
    assert sorted(wanted - passed) == []
