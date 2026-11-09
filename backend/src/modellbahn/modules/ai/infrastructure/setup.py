"""Which writer the settings ask for (``MB_AI_PROVIDER``), built once per process."""

from modellbahn.modules.ai.application.ports import CopyWriter
from modellbahn.modules.ai.infrastructure.claude import ClaudeCopyWriter
from modellbahn.modules.ai.infrastructure.fake import FAKE_MODEL, FakeCopyWriter
from modellbahn.platform.config import AiProvider, Settings


def build_copy_writer(settings: Settings) -> CopyWriter | None:
    """The model behind the drafts, or None while drafts are switched off."""
    match settings.ai_provider:
        case AiProvider.OFF:
            return None
        case AiProvider.FAKE:
            return FakeCopyWriter()
        case AiProvider.ANTHROPIC:
            return ClaudeCopyWriter(
                api_key=settings.anthropic_api_key.get_secret_value().strip(),
                model=settings.ai_model,
                effort=settings.ai_effort,
                base_url=settings.anthropic_api_url,
            )


def model_label(settings: Settings) -> str:
    """The model the Stellwerk names next to the button."""
    return FAKE_MODEL if settings.ai_provider is AiProvider.FAKE else settings.ai_model
