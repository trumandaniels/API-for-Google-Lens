"""HTTP route definitions for the Google Lens challenge API."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from app.errors import LensApiError, to_http_error
from app.lens.service import GoogleLensService
from app.models import ImageUrl, ProviderApiToken
from app.observability import (
    UNPARSED_IMAGE_URL_HASH,
    get_api_logger,
    hash_url as hash_image_url,
    log_lens_api_request_completed,
    log_lens_api_request_failed,
    log_lens_api_request_started,
)

router = APIRouter()
LOGGER = get_api_logger()


def get_lens_service(request: Request) -> GoogleLensService:
    """Return the process-scoped Google Lens service.

    Args:
        request: Current FastAPI request.

    Returns:
        Shared service configured during application startup.

    Example:
        >>> from types import SimpleNamespace
        >>> request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(lens_service="service")))
        >>> get_lens_service(request)
        'service'
    """
    return request.app.state.lens_service


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Return a minimal health check response.

    Returns:
        JSON object indicating that the process is responsive.

    Example:
        >>> import asyncio
        >>> asyncio.run(healthz())
        {'status': 'ok'}
    """
    return {"status": "ok"}


@router.get("/google-lens", response_class=HTMLResponse)
async def google_lens(
    imageUrl: str = Query(..., description="Public image URL to search with Google Lens."),
    mrscraper_api_key: str | None = Header(
        default=None,
        alias="X-MrScraper-Api-Key",
        description="Optional per-request MrScraper token override.",
        include_in_schema=False,
    ),
    service: GoogleLensService = Depends(get_lens_service),
) -> HTMLResponse:
    """Return raw Google Lens Exact Match HTML for an image URL.

    Args:
        imageUrl: URL of the image to submit to Google Lens.
        mrscraper_api_key: Optional per-request MrScraper token override. This
            lets callers retry with their own MrScraper account when the
            unauthenticated deployment is out of credits.
        service: Configured Google Lens service.

    Returns:
        HTML response containing the upstream Exact Match page.

    Raises:
        HTTPException: Returned when input parsing, upstream fetching, or
            response classification fails.

    Example:
        >>> import asyncio
        >>> from app.models import ExactMatchHtml
        >>> class FakeService:
        ...     async def fetch_exact_match_html(self, image_url, token_override=None):
        ...         return ExactMatchHtml("<html>Exact matches</html>", "https://www.google.com/search?udm=48")
        >>> response = asyncio.run(google_lens("https://example.com/a.jpg", mrscraper_api_key=None, service=FakeService()))
        >>> response.status_code
        200
    """
    started = time.perf_counter()
    image_url_hash = UNPARSED_IMAGE_URL_HASH
    token_override = ProviderApiToken.parse_optional(mrscraper_api_key)
    token_override_present = token_override is not None

    try:
        parsed_url = ImageUrl.parse(imageUrl)
        image_url_hash = hash_image_url(parsed_url.value)
        log_lens_api_request_started(LOGGER, image_url_hash, token_override_present)
        result = await service.fetch_exact_match_html(parsed_url, token_override)
    except LensApiError as error:
        http_error = to_http_error(error)
        log_lens_api_request_failed(
            LOGGER,
            image_url_hash,
            http_error.status_code,
            type(error).__name__,
            (time.perf_counter() - started) * 1000,
            token_override_present,
        )
        raise HTTPException(status_code=http_error.status_code, detail=http_error.detail) from error

    log_lens_api_request_completed(
        LOGGER,
        image_url_hash,
        (time.perf_counter() - started) * 1000,
        len(result.html.encode("utf-8")),
        "udm=48" in result.source_url,
        token_override_present,
    )
    return HTMLResponse(content=result.html, status_code=200)
