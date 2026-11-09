"""A writer without a model, for development and tests (``MB_AI_PROVIDER=fake``).

It builds a plain draft from the facts so the Stellwerk's review can be tried without
an API key and without cost. The production settings refuse it.
"""

from typing import Final

from modellbahn.modules.ai.application.ports import CopyFacts, CopyWriterError, WrittenCopy
from modellbahn.modules.ai.domain.model import CopyDraft, FailureReason, Usage
from modellbahn.platform.events import JsonValue

FAKE_MODEL: Final = "fake"
FAKE_PROMPT_VERSION: Final = "fake-1"
FAIL_MARKER: Final = "[ki-fehler]"
"""A product whose name holds this fails, to try the failure path by hand."""


def _texts(values: JsonValue) -> list[str]:
    return [str(v) for v in values] if isinstance(values, list) else []


class FakeCopyWriter:
    def __init__(self) -> None:
        self.calls: list[CopyFacts] = []

    @property
    def model(self) -> str:
        return FAKE_MODEL

    async def aclose(self) -> None:
        return None

    async def write(self, facts: CopyFacts) -> WrittenCopy:
        self.calls.append(facts)
        if FAIL_MARKER in facts.name.lower():
            raise CopyWriterError(
                FailureReason.INVALID_OUTPUT,
                "Testfehler auf Wunsch des Produktnamens",
                model=FAKE_MODEL,
                prompt_version=FAKE_PROMPT_VERSION,
            )
        data = facts.facts
        scales = data.get("massstaebe")
        scale_texts: list[str] = []
        finishes: list[str] = []
        if isinstance(scales, list):
            for scale in scales:
                if isinstance(scale, dict):
                    scale_texts.append(f"{scale.get('massstab')} ({scale.get('verhaeltnis')})")
                    finishes.extend(_texts(scale.get("ausfuehrungen")))
        in_scales = " und ".join(scale_texts) or "einem Maßstab"
        as_finishes = " oder ".join(dict.fromkeys(finishes)) or "Modell"
        prototype = str(data.get("vorbild") or "").strip()
        questions = [] if prototype else ["Welches Vorbild hat das Modell genau?"]
        description = "\n\n".join(
            part
            for part in (
                prototype or f"Das Vorbild des Modells {facts.name} beschreibt die Werkstatt noch.",
                f"Das Modell gibt es in {in_scales}, als {as_finishes}.",
                "Dieser Text ist ein Testentwurf ohne Sprachmodell.",
            )
            if part
        )
        return WrittenCopy(
            draft=CopyDraft.clean(
                f"{facts.name} in {in_scales} als {as_finishes}.", description, questions
            ),
            usage=Usage(input_tokens=1200, output_tokens=300, cost_micro_usd=0),
            model=FAKE_MODEL,
            prompt_version=FAKE_PROMPT_VERSION,
        )
