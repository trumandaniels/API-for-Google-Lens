"""FastAPI application factory for the Google Lens Exact Match API.

Example:
    Run locally with Uvicorn:

        uvicorn app.main:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI

from app.api import router


def create_app() -> FastAPI:
    """Create the FastAPI application.

    Returns:
        Configured FastAPI application with challenge routes registered.
    """
    application = FastAPI(
        title="Google Lens Exact Match API",
        version="0.1.0",
        description="Returns raw Exact Match HTML for an image URL.",
    )
    application.include_router(router)
    return application


app = create_app()

