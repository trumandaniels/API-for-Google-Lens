"""FastAPI application factory for the Google Lens Exact Match API.

Example:
    Run locally with Uvicorn:

        uvicorn app.main:app --reload
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import router
from app.config import Settings, get_settings
from app.lens.service import GoogleLensService
from app.throttling import AsyncConcurrencyLimiter


def build_lens_service(settings: Settings) -> GoogleLensService:
    """Build the process-scoped Lens service.

    Args:
        settings: Parsed application settings.

    Returns:
        Service with shared client configuration and concurrency limiter.
    """
    limiter = AsyncConcurrencyLimiter(settings.max_concurrency)
    return GoogleLensService.from_settings(settings=settings, limiter=limiter)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the FastAPI application.

    Args:
        settings: Optional settings override used by deterministic tests.

    Returns:
        Configured FastAPI application with challenge routes registered.
    """
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        """Initialize shared application state for the process lifetime."""
        resolved_settings = settings if settings is not None else get_settings()
        application.state.settings = resolved_settings
        application.state.lens_service = build_lens_service(resolved_settings)
        yield

    application = FastAPI(
        title="Google Lens Exact Match API",
        version="0.1.0",
        description="Returns raw Exact Match HTML for an image URL.",
        lifespan=lifespan,
    )
    application.include_router(router)
    return application


app = create_app()
