"""Claude writes the drafts (ADR 0021): one request per product, the answer as JSON.

The system prompt is the same for every product and cached; the facts and up to two
photos follow as the user's message. Structured outputs hold the answer to the schema,
and the server-side fallback hands a request Claude's safety filters decline to
another model instead of returning the refusal.

What a call costs is worked out here from the token counts and the price table
below: the provider bills in dollars per million tokens, which is exactly millionths
of a dollar per token.
"""

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from importlib.resources import files
from typing import Any, Final, cast

import anthropic
import httpx2
import structlog
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessage,
    BetaMessageParam,
    BetaOutputConfigParam,
    BetaTextBlockParam,
    BetaUsage,
)

from modellbahn.modules.ai.application.ports import CopyFacts, CopyWriterError, WrittenCopy
from modellbahn.modules.ai.domain.model import CopyDraft, FailureReason, Usage
from modellbahn.platform.config import AiEffort

PROMPT_VERSION: Final = "product-copy-1"
"""Changes with every edit of the prompt or the schema, so runs show what they used."""
SYSTEM_PROMPT: Final = (
    files("modellbahn.modules.ai.infrastructure") / "prompts" / "product_copy.md"
).read_text(encoding="utf-8")
MAX_TOKENS: Final = 8000
"""Thinking and answer together; a description needs a fraction of it."""
TIMEOUT_SECONDS: Final = 300.0
"""Well below the ten minutes after which the worker counts a run as lost."""
FALLBACK_BETA: Final = "server-side-fallback-2026-07-01"

COPY_SCHEMA: Final[dict[str, object]] = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "Kurztext für Kacheln und Listen, ein Satz.",
        },
        "description": {
            "type": "string",
            "description": "Beschreibung der Produktseite, Absätze durch Leerzeilen getrennt.",
        },
        "open_questions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Fragen an die Werkstatt zu fehlenden oder unsicheren Fakten.",
        },
    },
    "required": ["summary", "description", "open_questions"],
    "additionalProperties": False,
}

_logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Price:
    """Dollars per million tokens, which is millionths of a dollar per token."""

    input: Decimal
    output: Decimal
    cache_read: Decimal

    @property
    def cache_write(self) -> Decimal:
        # Five-minute cache writes cost a quarter more than plain input.
        return self.input * Decimal("1.25")


PRICES: Final[Mapping[str, Price]] = {
    "claude-fable-5-1": Price(Decimal(10), Decimal(50), Decimal("0.25")),
    "claude-opus-5-5": Price(Decimal(4), Decimal(20), Decimal("0.20")),
    "claude-opus-5": Price(Decimal(5), Decimal(25), Decimal("0.50")),
    "claude-opus-4-8": Price(Decimal(5), Decimal(25), Decimal("0.50")),
    "claude-sonnet-5-5": Price(Decimal(2), Decimal(10), Decimal("0.20")),
    "claude-sonnet-5": Price(Decimal(2), Decimal(10), Decimal("0.20")),
    "claude-haiku-5-5": Price(Decimal("0.10"), Decimal("0.50"), Decimal("0.01")),
}
UNKNOWN_PRICE: Final = PRICES["claude-fable-5-1"]
"""A model missing from the table counts at the dearest price: the budget errs on the safe side."""


def price_of(model: str) -> Price:
    """The price of the model; dated ids (``claude-opus-5-5-20261001``) match their family."""
    matches = [name for name in PRICES if model == name or model.startswith(f"{name}-")]
    return PRICES[max(matches, key=len)] if matches else UNKNOWN_PRICE


def cost_micro_usd(
    model: str, *, input_tokens: int, output_tokens: int, cache_read: int, cache_write: int
) -> int:
    price = price_of(model)
    total = (
        input_tokens * price.input
        + output_tokens * price.output
        + cache_read * price.cache_read
        + cache_write * price.cache_write
    )
    return int(total.to_integral_value(rounding=ROUND_HALF_UP))


def usage_of(message: BetaMessage, *, requested_model: str) -> Usage:
    """Tokens and cost of the response; with a fallback, each model at its own price."""
    usage: BetaUsage = message.usage
    parts: list[tuple[str, int, int, int, int]] = [
        (
            getattr(item, "model", None) or requested_model,
            item.input_tokens,
            item.output_tokens,
            item.cache_read_input_tokens or 0,
            item.cache_creation_input_tokens or 0,
        )
        for item in usage.iterations or ()
        if item.type in {"message", "fallback_message"}
    ]
    if not parts:
        parts = [
            (
                message.model or requested_model,
                usage.input_tokens,
                usage.output_tokens,
                usage.cache_read_input_tokens or 0,
                usage.cache_creation_input_tokens or 0,
            )
        ]
    return Usage(
        input_tokens=sum(p[1] for p in parts),
        output_tokens=sum(p[2] for p in parts),
        cache_read_tokens=sum(p[3] for p in parts),
        cache_write_tokens=sum(p[4] for p in parts),
        cost_micro_usd=sum(
            cost_micro_usd(model, input_tokens=i, output_tokens=o, cache_read=r, cache_write=w)
            for model, i, o, r, w in parts
        ),
    )


def user_content(facts: CopyFacts, *, with_photos: bool) -> list[dict[str, Any]]:
    """The photos first (Claude reads images before the text about them), then the facts."""
    photos: Iterable[str] = facts.image_urls if with_photos else ()
    blocks: list[dict[str, Any]] = [
        {"type": "image", "source": {"type": "url", "url": url}} for url in photos
    ]
    count = len(blocks)
    intro = (
        f"Fakten zum Modell als JSON, dazu {count} Foto{'s' if count != 1 else ''} oben:"
        if count
        else "Fakten zum Modell als JSON (ohne Foto):"
    )
    blocks.append(
        {
            "type": "text",
            "text": f"{intro}\n\n{json.dumps(facts.facts, ensure_ascii=False, indent=2)}",
        }
    )
    return blocks


def draft_of(message: BetaMessage) -> CopyDraft:
    """The draft from the answer's text; raises ValueError if it is no valid draft."""
    text = "".join(block.text for block in message.content if block.type == "text")
    data = json.loads(text)
    if not isinstance(data, dict):
        msg = "the answer is not a JSON object"
        raise ValueError(msg)
    summary, description = data.get("summary"), data.get("description")
    questions = data.get("open_questions", [])
    if not isinstance(summary, str) or not isinstance(description, str):
        msg = "summary and description must be text"
        raise ValueError(msg)
    if not isinstance(questions, list):
        msg = "open_questions must be a list"
        raise ValueError(msg)
    draft = CopyDraft.clean(summary, description, (str(q) for q in questions))
    if not draft.summary or not draft.description:
        msg = "summary or description is empty"
        raise ValueError(msg)
    return draft


class ClaudeCopyWriter:
    """The :class:`CopyWriter` behind Anthropic's Messages API."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        effort: AiEffort,
        base_url: str = "https://api.anthropic.com",
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        self._model = model
        self._effort = effort
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key,
            base_url=base_url,
            timeout=TIMEOUT_SECONDS,
            max_retries=2,
            http_client=http_client,
        )

    @property
    def model(self) -> str:
        return self._model

    async def aclose(self) -> None:
        await self._client.close()

    async def write(self, facts: CopyFacts) -> WrittenCopy:
        try:
            message = await self._send(facts, with_photos=True)
        except anthropic.BadRequestError as error:
            if not facts.image_urls:
                raise self._error(FailureReason.PROVIDER, _detail(error)) from error
            # Most often the provider could not fetch a photo: the facts alone still do.
            _logger.warning(
                "ai.copy.photos_rejected", product_id=str(facts.product_id), detail=_detail(error)
            )
            try:
                message = await self._send(facts, with_photos=False)
            except anthropic.APIError as retry_error:
                raise self._from_api_error(retry_error) from retry_error
        except anthropic.APIError as error:
            raise self._from_api_error(error) from error
        return self._written(message)

    async def _send(self, facts: CopyFacts, *, with_photos: bool) -> BetaMessage:
        system: list[BetaTextBlockParam] = [
            {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
        ]
        content = cast("list[BetaContentBlockParam]", user_content(facts, with_photos=with_photos))
        messages: list[BetaMessageParam] = [{"role": "user", "content": content}]
        output_config: BetaOutputConfigParam = {
            "effort": self._effort,
            "format": {"type": "json_schema", "schema": COPY_SCHEMA},
        }
        message: BetaMessage = await self._client.beta.messages.create(
            model=self._model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=messages,
            output_config=output_config,
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        return message

    def _written(self, message: BetaMessage) -> WrittenCopy:
        usage = usage_of(message, requested_model=self._model)
        model = message.model or self._model
        if message.stop_reason == "refusal":
            raise self._error(
                FailureReason.REFUSED,
                "Claude hat den Text abgelehnt, das Ausweichmodell auch.",
                usage=usage,
                model=model,
            )
        if message.stop_reason in {"max_tokens", "model_context_window_exceeded"}:
            raise self._error(
                FailureReason.TRUNCATED,
                "Die Antwort passte nicht in die Grenze der Tokens.",
                usage=usage,
                model=model,
            )
        try:
            draft = draft_of(message)
        except ValueError as error:
            raise self._error(
                FailureReason.INVALID_OUTPUT, str(error), usage=usage, model=model
            ) from error
        return WrittenCopy(draft=draft, usage=usage, model=model, prompt_version=PROMPT_VERSION)

    def _from_api_error(self, error: anthropic.APIError) -> CopyWriterError:
        if isinstance(error, anthropic.AuthenticationError | anthropic.PermissionDeniedError):
            return self._error(
                FailureReason.PROVIDER,
                f"Der API-Schlüssel wurde abgelehnt ({_detail(error)}).",
            )
        retryable = isinstance(
            error,
            anthropic.APIConnectionError | anthropic.RateLimitError | anthropic.InternalServerError,
        ) or (isinstance(error, anthropic.APIStatusError) and error.status_code >= 500)  # noqa: PLR2004
        return self._error(FailureReason.PROVIDER, _detail(error), retryable=retryable)

    def _error(
        self,
        reason: FailureReason,
        detail: str,
        *,
        usage: Usage | None = None,
        model: str = "",
        retryable: bool = False,
    ) -> CopyWriterError:
        return CopyWriterError(
            reason,
            detail,
            usage=usage,
            model=model or self._model,
            prompt_version=PROMPT_VERSION,
            retryable=retryable,
        )


def _detail(error: anthropic.APIError) -> str:
    """Status and the provider's message, never the request (it holds no key, but still)."""
    status = getattr(error, "status_code", None)
    body = getattr(error, "body", None)
    message = ""
    if isinstance(body, dict):
        inner = body.get("error")
        if isinstance(inner, dict):
            message = str(inner.get("message", ""))
    text = message or error.message or type(error).__name__
    return f"{status}: {text}" if status else text
