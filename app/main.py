"""FastAPI application factory for the Google Lens Exact Match API.

Example:
    Run locally with Uvicorn:

        uvicorn app.main:app --reload
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging

import httpx
from fastapi import FastAPI

from app.api import router
from app.config import Settings, get_settings
from app.lens.service import GoogleLensService
from app.throttling import AsyncConcurrencyLimiter


APPLICATION_LOGGER_NAMES = ("uvicorn.error", "app")


def configure_application_logging(settings: Settings) -> None:
    """Apply parsed application log level to app-owned loggers.

    Args:
        settings: Parsed process settings containing the configured log level.

    Example:
        >>> settings = Settings(mrscraper_api_key="token", log_level="DEBUG")
        >>> configure_application_logging(settings)
        >>> logging.getLogger("app").level == logging.DEBUG
        True
    """

    level = getattr(logging, settings.log_level)
    for logger_name in APPLICATION_LOGGER_NAMES:
        logging.getLogger(logger_name).setLevel(level)


def build_lens_service(settings: Settings) -> GoogleLensService:
    """Build the process-scoped Lens service.

    Args:
        settings: Parsed application settings.

    Returns:
        Service with shared client configuration and concurrency limiter.

    Example:
        >>> import asyncio
        >>> settings = Settings(mrscraper_api_key="token")
        >>> service = build_lens_service(settings)
        >>> isinstance(service, GoogleLensService)
        True
        >>> asyncio.run(service.aclose())
    """
    limiter = AsyncConcurrencyLimiter(settings.max_concurrency)
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": settings.user_agent,
        "x-api-token": settings.mrscraper_api_key,
    }
    http_client = httpx.AsyncClient(
        follow_redirects=True,
        headers=headers,
        limits=httpx.Limits(
            max_connections=max(settings.max_concurrency * 2, 20),
            max_keepalive_connections=max(settings.max_concurrency, 10),
        ),
        timeout=httpx.Timeout(settings.request_timeout_seconds),
        trust_env=False,
    )
    return GoogleLensService.from_settings(
        settings=settings,
        limiter=limiter,
        http_client=http_client,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the FastAPI application.

    Args:
        settings: Optional settings override used by deterministic tests.

    Returns:
        Configured FastAPI application with challenge routes registered.

    Example:
        >>> settings = Settings(mrscraper_api_key="token")
        >>> application = create_app(settings)
        >>> application.title
        'Google Lens Exact Match API'
    """
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        """Initialize shared application state for the process lifetime."""
        resolved_settings = settings if settings is not None else get_settings()
        configure_application_logging(resolved_settings)
        lens_service = build_lens_service(resolved_settings)
        application.state.settings = resolved_settings
        application.state.lens_service = lens_service
        try:
            yield
        finally:
            await lens_service.aclose()

    application = FastAPI(
        title="Google Lens Exact Match API",
        version="0.1.0",
        description="Returns raw Exact Match HTML for an image URL.",
        lifespan=lifespan,
    )
    application.include_router(router)
    return application


app = create_app()
