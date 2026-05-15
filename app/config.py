"""Application configuration parsing.

Configuration is parsed at process boundary from environment variables and
stored as a typed value before it reaches request handling code.
"""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel, Field, ValidationError, field_validator


class Settings(BaseModel):
    """Runtime settings for the Google Lens API.

    Attributes:
        google_base_url: Base Google Lens upload-by-URL endpoint used for direct requests.
        request_timeout_seconds: Upstream request timeout in seconds.
        max_concurrency: Maximum in-process concurrent upstream requests.
        user_agent: User agent sent to Google.
        proxy_url: Optional outbound proxy URL.
    """

    google_base_url: str = Field(default="https://lens.google.com/uploadbyurl")
    request_timeout_seconds: float = Field(default=30.0, gt=0)
    max_concurrency: int = Field(default=4, gt=0)
    user_agent: str = Field(
        default=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
        min_length=1,
    )
    proxy_url: str | None = None

    @field_validator("google_base_url")
    @classmethod
    def require_https_google_url(cls, value: str) -> str:
        """Parse and constrain the configured Google base URL.

        Args:
            value: Candidate Google base URL.

        Returns:
            Normalized URL string.

        Raises:
            ValueError: If the URL is not an HTTPS URL.
        """
        if not value.startswith("https://"):
            raise ValueError("google_base_url must be an HTTPS URL")
        return value.rstrip("?")


def parse_settings(environ: dict[str, str]) -> Settings:
    """Parse settings from an environment mapping.

    Args:
        environ: Environment-style mapping, usually `os.environ`.

    Returns:
        Parsed settings.

    Raises:
        ValidationError: If environment values cannot be parsed into settings.
    """
    return Settings(
        google_base_url=environ.get("GOOGLE_BASE_URL", Settings().google_base_url),
        request_timeout_seconds=environ.get(
            "REQUEST_TIMEOUT_SECONDS",
            str(Settings().request_timeout_seconds),
        ),
        max_concurrency=environ.get("MAX_CONCURRENCY", str(Settings().max_concurrency)),
        user_agent=environ.get("USER_AGENT", Settings().user_agent),
        proxy_url=environ.get("PROXY_URL") or None,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached process settings.

    Returns:
        Settings parsed from `os.environ`.

    Raises:
        ValidationError: If process environment values are invalid.
    """
    try:
        return parse_settings(os.environ)
    except ValidationError:
        raise
