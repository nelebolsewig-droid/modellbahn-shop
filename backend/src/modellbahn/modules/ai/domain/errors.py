"""Errors of the AI module; the API turns them into problem responses."""


class AiError(Exception):
    """Base class of the AI module's domain errors."""


class InvalidFieldError(AiError):
    """A value breaks a rule of the model (for example an unknown field to apply)."""

    def __init__(self, field: str, code: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field
        self.code = code
        self.message = message


class AiDisabledError(AiError):
    """No language model is configured (``MB_AI_PROVIDER=off``)."""


class ProductNotFoundError(AiError):
    """The product to write about does not exist."""


class RunNotFoundError(AiError):
    """No such run."""


class RunNotReviewableError(AiError):
    """The run has no draft to take over, or it was reviewed already."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"the run cannot be reviewed: {reason}")
        self.reason = reason
