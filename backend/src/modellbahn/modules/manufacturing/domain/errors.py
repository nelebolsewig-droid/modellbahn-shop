"""Errors of the manufacturing domain. The API layer decides how they are presented."""


class ManufacturingError(Exception):
    """Base of every error raised by the manufacturing module."""


class InvalidFieldError(ManufacturingError):
    """A value breaks a rule of the model (length, format, range, a duplicate)."""

    def __init__(self, field: str, code: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field
        self.code = code
        self.message = message


class PrinterNotFoundError(ManufacturingError):
    pass


class PrinterInUseError(ManufacturingError):
    """The printer has print jobs; it keeps its history and can be retired, not removed."""


class PrinterUnavailableError(ManufacturingError):
    """The printer cannot take this now.

    ``reason`` is ``busy`` (another job is printing on it), ``not_in_service`` (defective,
    in repair or retired: nothing starts on it), ``retired`` (no new jobs at all), or
    ``has_queue`` (jobs wait for it, so it cannot be retired yet).
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"the printer is unavailable: {reason}")
        self.reason = reason


class MaterialNotFoundError(ManufacturingError):
    pass


class MaterialInUseError(ManufacturingError):
    """Parts are made of the material; it can be archived, not removed."""


class PartNotFoundError(ManufacturingError):
    pass


class PartInUseError(ManufacturingError):
    """The part is in a bill of materials or was printed; it can be archived, not removed."""


class ProductScaleNotFoundError(ManufacturingError):
    """The catalogue knows no such product in a scale."""


class PrintJobNotFoundError(ManufacturingError):
    pass


class InvalidPrintJobStateError(ManufacturingError):
    """The job's state does not allow this (e.g. starting a job that is already done)."""

    def __init__(self, status: str) -> None:
        super().__init__(f"not possible while the job is {status}")
        self.status = status
