"""Domain errors and HTTP error mapping for the Google Lens API."""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus


@dataclass
class LensApiError(Exception):
    """Base domain error for request handling failures.

    Attributes:
        message: Human-readable failure detail safe for API clients.
    """

    message: str


@dataclass
class MalformedImageUrlError(LensApiError):
    """Raised when the `imageUrl` query parameter cannot be parsed."""


@dataclass
class UpstreamRequestError(LensApiError):
    """Raised when the direct Google request fails before classification."""


@dataclass
class UpstreamTimeoutError(LensApiError):
    """Raised when the direct Google request exceeds the configured timeout."""


@dataclass
class BotBlockError(LensApiError):
    """Raised when Google returns CAPTCHA, bot-check, or block content."""


@dataclass
class GoogleErrorPageError(LensApiError):
    """Raised when Google returns a non-result error page."""


@dataclass
class ExactMatchNotFoundError(LensApiError):
    """Raised when upstream HTML is not recognized as Exact Match content."""


@dataclass(frozen=True)
class HttpError:
    """Framework-neutral HTTP error mapping.

    Attributes:
        status_code: HTTP status code to return.
        detail: API-safe error detail.
    """

    status_code: int
    detail: str


ERROR_STATUS_MAP: dict[type[LensApiError], HTTPStatus] = {
    MalformedImageUrlError: HTTPStatus.BAD_REQUEST,
    UpstreamTimeoutError: HTTPStatus.GATEWAY_TIMEOUT,
    UpstreamRequestError: HTTPStatus.BAD_GATEWAY,
    BotBlockError: HTTPStatus.TOO_MANY_REQUESTS,
    GoogleErrorPageError: HTTPStatus.BAD_GATEWAY,
    ExactMatchNotFoundError: HTTPStatus.BAD_GATEWAY,
}


def to_http_error(error: LensApiError) -> HttpError:
    """Convert a domain error into framework-neutral HTTP error details.

    Args:
        error: Domain error raised by request parsing or the Lens service.

    Returns:
        HTTP status code and detail.
    """
    status = ERROR_STATUS_MAP.get(type(error), HTTPStatus.INTERNAL_SERVER_ERROR)
    return HttpError(status_code=int(status), detail=error.message)
