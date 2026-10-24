"""Error model of the API: application errors rendered as RFC 9457 problem details.

Every error response has the media type ``application/problem+json`` and the body
``{"type", "title", "status", "detail", "code"}``; validation errors add
``errors: [{"field", "code", "message"}]``. ``code`` is the stable, machine-readable
part: the frontend translates it, titles and details stay English.
"""

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, ClassVar, Final

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_MEDIA_TYPE: Final = "application/problem+json"
# An outage of the database is usually a restart; clients may try again soon.
DATABASE_RETRY_AFTER_SECONDS: Final = 5


@dataclass(frozen=True, slots=True)
class FieldError:
    """One invalid input field."""

    field: str
    code: str
    message: str


class AppError(Exception):
    """Base of all errors that the API turns into a problem response.

    Subclasses fix the HTTP status and a default ``code``; a raise site may pass a
    more specific ``code`` (e.g. ``invalid_credentials`` for a 401).
    """

    status: ClassVar[int] = 500
    default_code: ClassVar[str] = "internal_error"

    def __init__(
        self,
        detail: str | None = None,
        *,
        code: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.code = code or self.default_code
        self.detail = detail or HTTPStatus(self.status).description
        self.headers = headers
        super().__init__(self.detail)

    @property
    def title(self) -> str:
        """Short English summary: the HTTP reason phrase of :attr:`status`."""
        return HTTPStatus(self.status).phrase


class BadRequestError(AppError):
    """400: the request is understood but cannot be carried out as it is."""

    status = 400
    default_code = "bad_request"


class UnauthorizedError(AppError):
    """401: no valid session, or failed login."""

    status = 401
    default_code = "not_authenticated"


class ForbiddenError(AppError):
    """403: authenticated or not, this is not allowed."""

    status = 403
    default_code = "forbidden"


class NotFoundError(AppError):
    """404: the addressed resource does not exist."""

    status = 404
    default_code = "not_found"


class ConflictError(AppError):
    """409: the request conflicts with the current state."""

    status = 409
    default_code = "conflict"


class PreconditionFailedError(AppError):
    """412: ``If-Match`` names a version that is no longer current."""

    status = 412
    default_code = "precondition_failed"


class UnsupportedMediaTypeError(AppError):
    """415: the body is not JSON."""

    status = 415
    default_code = "unsupported_media_type"


class ValidationFailedError(AppError):
    """422: invalid input; ``errors`` names each offending field.

    A more specific ``code`` marks a rule rather than plain input validation, e.g.
    ``not_publishable`` with one entry per missing piece.
    """

    status = 422
    default_code = "validation_failed"

    def __init__(
        self, errors: Sequence[FieldError], detail: str | None = None, *, code: str | None = None
    ) -> None:
        super().__init__(detail or "The request contains invalid fields.", code=code)
        self.errors = list(errors)


class PreconditionRequiredError(AppError):
    """428: the route overwrites state and needs ``If-Match`` with the version read."""

    status = 428
    default_code = "precondition_required"


class TooManyRequestsError(AppError):
    """429: the client sent too many requests of a kind; ``Retry-After`` says when to retry."""

    status = 429
    default_code = "too_many_requests"


class ServiceUnavailableError(AppError):
    """503: a dependency such as the database is not available."""

    status = 503
    default_code = "service_unavailable"


class ProblemFieldError(BaseModel):
    """OpenAPI schema of one entry in ``errors``."""

    field: str = Field(examples=["email"])
    code: str = Field(examples=["invalid"])
    message: str


class Problem(BaseModel):
    """OpenAPI schema of an RFC 9457 problem response."""

    type: str = Field(examples=["/problems/invalid-credentials"])
    title: str = Field(examples=["Unauthorized"])
    status: int = Field(examples=[401])
    detail: str
    code: str = Field(examples=["invalid_credentials"])


class ValidationProblem(Problem):
    """OpenAPI schema of a 422 problem response."""

    type: str = Field(examples=["/problems/validation-failed"])
    title: str = Field(examples=["Unprocessable Content"])
    status: int = Field(examples=[422])
    code: str = Field(examples=["validation_failed"])
    errors: list[ProblemFieldError]


PROBLEM_SCHEMA_MODELS: Final = (Problem, ValidationProblem)
_SCHEMA_REF_TEMPLATE: Final = "#/components/schemas/{model}"


def problem_responses(codes: Mapping[int, Iterable[str]]) -> dict[int | str, dict[str, Any]]:
    """``responses=`` entries documenting the problem bodies of a route.

    ``codes`` maps each status to the problem codes the route can answer with; they
    are listed in the description so that client authors know what to translate.
    The referenced schemas are added by :func:`add_problem_schemas`.
    """
    responses: dict[int | str, dict[str, Any]] = {}
    for status, status_codes in sorted(codes.items()):
        model = ValidationProblem if status == HTTPStatus.UNPROCESSABLE_CONTENT else Problem
        listed = ", ".join(f"`{code}`" for code in sorted(set(status_codes)))
        responses[status] = {
            "description": f"{HTTPStatus(status).phrase}. Problem codes: {listed}.",
            "content": {
                PROBLEM_MEDIA_TYPE: {
                    "schema": {"$ref": _SCHEMA_REF_TEMPLATE.format(model=model.__name__)}
                }
            },
        }
    return responses


_CSRF_PROBLEMS: Final[Mapping[int, Sequence[str]]] = {
    403: ["csrf_header_missing"],
    415: ["unsupported_media_type"],
}
_VALIDATION_PROBLEMS: Final[Mapping[int, Sequence[str]]] = {422: ["validation_failed"]}
# Every route of the modules reads or writes the database (if only to check the session).
_DATABASE_PROBLEMS: Final[Mapping[int, Sequence[str]]] = {503: ["database_unavailable"]}
_RATE_LIMIT_PROBLEMS: Final[Mapping[int, Sequence[str]]] = {429: ["too_many_requests"]}


def problems(
    codes: Mapping[int, Sequence[str]] | None = None,
    *,
    unsafe: bool = True,
    validated: bool = True,
    rate_limited: bool = False,
) -> dict[int | str, dict[str, Any]]:
    """OpenAPI ``responses`` of a module route: its own problem codes plus the common ones.

    ``unsafe`` routes (POST, PUT, PATCH, DELETE) pass the CSRF guard; ``validated``
    routes have a body or parameters that can fail validation; ``rate_limited`` routes
    use a :func:`~modellbahn.platform.ratelimit.rate_limit` dependency. Every route can
    find the database unavailable.
    """
    merged: defaultdict[int, list[str]] = defaultdict(list)
    sources = (
        _CSRF_PROBLEMS if unsafe else {},
        _VALIDATION_PROBLEMS if validated else {},
        _RATE_LIMIT_PROBLEMS if rate_limited else {},
        _DATABASE_PROBLEMS,
        codes or {},
    )
    for source in sources:
        for status, status_codes in source.items():
            merged[status].extend(status_codes)
    return problem_responses(merged)


def add_problem_schemas(openapi_schema: dict[str, Any]) -> dict[str, Any]:
    """Add the problem schemas that :func:`problem_responses` refers to.

    FastAPI only collects schemas of models it renders itself, and it would put them
    under ``application/json``; problem bodies are ``application/problem+json``.
    """
    schemas = openapi_schema.setdefault("components", {}).setdefault("schemas", {})
    for model in PROBLEM_SCHEMA_MODELS:
        schema = model.model_json_schema(ref_template=_SCHEMA_REF_TEMPLATE, mode="serialization")
        schemas.update(schema.pop("$defs", {}))
        schemas[model.__name__] = schema
    return openapi_schema


def problem_response(
    *,
    status: int,
    code: str,
    detail: str,
    errors: Sequence[FieldError] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Render a problem details response."""
    body: dict[str, Any] = {
        "type": f"/problems/{code.replace('_', '-')}",
        "title": HTTPStatus(status).phrase,
        "status": status,
        "detail": detail,
        "code": code,
    }
    if errors is not None:
        body["errors"] = [{"field": e.field, "code": e.code, "message": e.message} for e in errors]
    return JSONResponse(body, status_code=status, headers=headers, media_type=PROBLEM_MEDIA_TYPE)


def app_error_response(error: AppError) -> JSONResponse:
    """Render an :class:`AppError` as problem details."""
    errors = error.errors if isinstance(error, ValidationFailedError) else None
    return problem_response(
        status=error.status,
        code=error.code,
        detail=error.detail,
        errors=errors,
        headers=error.headers,
    )


def internal_error_response() -> JSONResponse:
    """The answer to an unexpected exception. Deliberately reveals nothing."""
    return problem_response(
        status=500, code="internal_error", detail="An unexpected error occurred."
    )


def database_unavailable_response() -> JSONResponse:
    """The answer when the database cannot be reached (503 ``database_unavailable``)."""
    return problem_response(
        status=503,
        code="database_unavailable",
        detail="The database is not reachable.",
        headers={"Retry-After": str(DATABASE_RETRY_AFTER_SECONDS)},
    )


def install_exception_handlers(app: FastAPI) -> None:
    """Make every error the framework knows about answer with problem details.

    Unexpected exceptions, including an unreachable database, are handled by the
    request context middleware in :mod:`modellbahn.platform.logging`, which knows
    the request id.
    """
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)


def add_error_translation[E: Exception](
    app: FastAPI, error_type: type[E], translate: Callable[[E], AppError]
) -> None:
    """Answer ``error_type`` (e.g. a module's domain errors) with ``translate(error)``.

    This keeps HTTP knowledge out of the domain: a module's API layer decides
    which status and code a domain error maps to.
    """

    async def handler(request: Request, exc: Exception) -> JSONResponse:
        if not isinstance(exc, error_type):  # pragma: no cover - guaranteed by Starlette
            raise exc
        return app_error_response(translate(exc))

    app.add_exception_handler(error_type, handler)


async def _handle_app_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppError):  # pragma: no cover - guaranteed by Starlette
        raise exc
    return app_error_response(exc)


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):  # pragma: no cover - guaranteed by Starlette
        raise exc
    errors = [_field_error(error) for error in exc.errors()]
    return app_error_response(ValidationFailedError(errors))


async def _handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):  # pragma: no cover - guaranteed by Starlette
        raise exc
    status = HTTPStatus(exc.status_code)
    code = status.phrase.lower().replace(" ", "_").replace("-", "_")
    # FastAPI's subclass allows any JSON as detail; the problem format wants a sentence.
    raw_detail: object = exc.detail
    detail = raw_detail if isinstance(raw_detail, str) else status.description
    return problem_response(status=status, code=code, detail=detail, headers=exc.headers)


# Pydantic's error types mapped to the small, stable vocabulary the frontend knows.
_FIELD_ERROR_CODES: Final = {
    "missing": "required",
    "string_too_short": "too_short",
    "string_too_long": "too_long",
    "json_invalid": "invalid_json",
    "extra_forbidden": "unknown_field",
}


def _field_error(error: Any) -> FieldError:
    error_type = str(error.get("type", ""))
    location = [str(part) for part in error.get("loc", ())]
    # The first element names where the value came from (body, query, ...); for
    # unparsable JSON the rest is a character offset, not a field.
    source, *path = location or [""]
    field = source if error_type == "json_invalid" or not path else ".".join(path)
    if error_type in _FIELD_ERROR_CODES:
        code = _FIELD_ERROR_CODES[error_type]
    elif error_type.endswith(("_type", "_parsing")):
        code = "invalid_type"
    else:
        code = "invalid"
    return FieldError(field=field, code=code, message=str(error.get("msg", "Invalid value.")))
