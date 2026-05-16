"""HTTP route definitions for the Google Lens challenge API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from app.errors import LensApiError, to_http_error
from app.lens.service import GoogleLensService
from app.models import ImageUrl, ProviderApiToken

router = APIRouter()


def get_lens_service(request: Request) -> GoogleLensService:
    """Return the process-scoped Google Lens service.

    Args:
        request: Current FastAPI request.

    Returns:
        Shared service configured during application startup.
    """
    return request.app.state.lens_service


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Return a minimal health check response.

    Returns:
        JSON object indicating that the process is responsive.
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
            is intended for trusted evaluator fallback use when the configured
            deployment token runs out of credits.
        service: Configured Google Lens service.

    Returns:
        HTML response containing the upstream Exact Match page.

    Raises:
        HTTPException: Returned when input parsing, upstream fetching, or
            response classification fails.
    """
    try:
        parsed_url = ImageUrl.parse(imageUrl)
        token_override = ProviderApiToken.parse_optional(mrscraper_api_key)
        result = await service.fetch_exact_match_html(parsed_url, token_override)
    except LensApiError as error:
        http_error = to_http_error(error)
        raise HTTPException(status_code=http_error.status_code, detail=http_error.detail) from error

    return HTMLResponse(content=result.html, status_code=200)
