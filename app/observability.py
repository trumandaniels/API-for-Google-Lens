"""Shared logging helpers for API requests and measurement tooling."""

from __future__ import annotations

import hashlib
import logging
from typing import Protocol

API_LOGGER_NAME = "uvicorn.error"
MEASUREMENT_LOGGER_NAME = "measure_lens_api"
DEFAULT_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
UNPARSED_IMAGE_URL_HASH = "unparsed"


class MeasurementLogResult(Protocol):
    """Typed surface needed to log one measurement result.

    Attributes:
        index: Zero-based request index.
        image_url_hash: Sanitized image URL hash.
        status_code: HTTP status code or `None` when the request failed before
            receiving a response.
        latency_seconds: End-to-end request latency.
        verdict: Aggregate verdict label.
        html_verdict: HTML classifier verdict label.
        error: Short failure detail, if any.
    """

    index: int
    image_url_hash: str
    status_code: int | None
    latency_seconds: float
    verdict: str
    html_verdict: str
    error: str | None


def get_api_logger() -> logging.Logger:
    """Return the logger used by FastAPI route and provider-hop logs.

    Returns:
        Logger attached to Uvicorn's error log stream.
    """

    return logging.getLogger(API_LOGGER_NAME)


def get_measurement_logger() -> logging.Logger:
    """Return the logger used by the measurement CLI.

    Returns:
        Logger dedicated to `scripts/measure_lens_api.py`.
    """

    return logging.getLogger(MEASUREMENT_LOGGER_NAME)


def configure_logging(
    verbose: bool,
    logger: logging.Logger | None = None,
) -> None:
    """Configure operator-facing command-line logging.

    Args:
        verbose: Whether to emit per-request progress logs.
        logger: Optional logger to set to the resolved level. When omitted,
            the measurement CLI logger is configured.
    """

    log_level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(level=log_level, format=DEFAULT_LOG_FORMAT)
    (logger or get_measurement_logger()).setLevel(log_level)


def hash_url(url: str) -> str:
    """Return a short stable hash for a URL.

    Args:
        url: URL whose raw value should not be emitted to logs.

    Returns:
        First 16 hex characters of the URL SHA-256 digest.
    """

    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def log_lens_api_request_started(
    logger: logging.Logger,
    image_url_hash: str,
    token_override_present: bool,
) -> None:
    """Log the start of a regular `/google-lens` request.

    Args:
        logger: Destination logger.
        image_url_hash: Sanitized image URL hash.
        token_override_present: Whether the caller supplied a provider token
            override header.
    """

    logger.info(
        "lens_api_request_started image_url_hash=%s token_override=%s",
        image_url_hash,
        token_override_present,
    )


def log_lens_api_request_failed(
    logger: logging.Logger,
    image_url_hash: str,
    status_code: int,
    error_type: str,
    elapsed_ms: float,
    token_override_present: bool,
) -> None:
    """Log a failed regular `/google-lens` request.

    Args:
        logger: Destination logger.
        image_url_hash: Sanitized image URL hash, or
            `UNPARSED_IMAGE_URL_HASH` when request parsing failed.
        status_code: HTTP status returned to the API caller.
        error_type: Domain error class name.
        elapsed_ms: Request duration in milliseconds.
        token_override_present: Whether the caller supplied a provider token
            override header.
    """

    logger.warning(
        (
            "lens_api_request_failed image_url_hash=%s status=%s "
            "error_type=%s elapsed_ms=%.0f token_override=%s"
        ),
        image_url_hash,
        status_code,
        error_type,
        elapsed_ms,
        token_override_present,
    )


def log_lens_api_request_completed(
    logger: logging.Logger,
    image_url_hash: str,
    elapsed_ms: float,
    response_bytes: int,
    source_url_has_udm_48: bool,
    token_override_present: bool,
) -> None:
    """Log a successful regular `/google-lens` request.

    Args:
        logger: Destination logger.
        image_url_hash: Sanitized image URL hash.
        elapsed_ms: Request duration in milliseconds.
        response_bytes: UTF-8 response body size.
        source_url_has_udm_48: Whether the final upstream source URL looked
            like the Exact Match tab.
        token_override_present: Whether the caller supplied a provider token
            override header.
    """

    logger.info(
        (
            "lens_api_request_completed image_url_hash=%s status=200 "
            "elapsed_ms=%.0f bytes=%s source_url_has_udm_48=%s "
            "token_override=%s"
        ),
        image_url_hash,
        elapsed_ms,
        response_bytes,
        source_url_has_udm_48,
        token_override_present,
    )


def log_measurement_result(
    result: MeasurementLogResult,
    logger: logging.Logger | None = None,
) -> None:
    """Log a sanitized per-request measurement result.

    Args:
        result: Completed measurement result. The log line intentionally uses
            the image URL hash instead of the raw URL and avoids response body
            details that may contain provider diagnostics.
        logger: Optional destination logger. When omitted, the measurement CLI
            logger is used.
    """

    (logger or get_measurement_logger()).info(
        (
            "request_completed index=%s image_url_hash=%s status=%s "
            "verdict=%s html_verdict=%s latency_seconds=%.3f has_error=%s"
        ),
        result.index,
        result.image_url_hash,
        result.status_code,
        result.verdict,
        result.html_verdict,
        result.latency_seconds,
        result.error is not None,
    )
