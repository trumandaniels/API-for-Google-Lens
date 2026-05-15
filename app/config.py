"""Application configuration parsing.

Configuration is parsed at process boundary from environment variables and
stored as a typed value before it reaches request handling code.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic import BaseModel, Field, ValidationError, field_validator


class Settings(BaseModel):
    """Runtime settings for the Google Lens API.

    Attributes:
        google_base_url: Base Google Lens upload-by-URL endpoint used for direct requests.
        request_timeout_seconds: Upstream request timeout in seconds.
        max_concurrency: Maximum in-process concurrent upstream requests.
        user_agent: User agent sent to Google.
        mrscraper_api_key: Optional MrScraper Scraper API token.
        mrscraper_api_url: MrScraper Scraper API endpoint.
        proxy_url: Optional outbound proxy URL. May be a generic proxy URL or
            a MrScraper proxy URL constructed from environment credentials.
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
    mrscraper_api_key: str | None = None
    mrscraper_api_url: str = Field(default="https://api.mrscraper.com")
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

    @field_validator("proxy_url")
    @classmethod
    def require_supported_proxy_url(cls, value: str | None) -> str | None:
        """Parse and constrain the optional outbound proxy URL.

        Args:
            value: Candidate proxy URL.

        Returns:
            Normalized proxy URL or `None`.

        Raises:
            ValueError: If the proxy URL does not use HTTP or HTTPS.
        """
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        if not stripped.startswith(("http://", "https://")):
            raise ValueError("proxy_url must start with http:// or https://")
        return stripped.rstrip("/")

    @field_validator("mrscraper_api_url")
    @classmethod
    def require_https_mrscraper_api_url(cls, value: str) -> str:
        """Parse and constrain the configured MrScraper API URL.

        Args:
            value: Candidate MrScraper Scraper API URL.

        Returns:
            Normalized URL string.

        Raises:
            ValueError: If the URL is not an HTTPS URL.
        """
        stripped = value.strip()
        if not stripped.startswith("https://"):
            raise ValueError("mrscraper_api_url must be an HTTPS URL")
        return stripped.rstrip("?")


def build_mrscraper_proxy_url(environ: dict[str, str]) -> str | None:
    """Build a MrScraper Residential Proxy URL from environment values.

    Args:
        environ: Environment-style mapping containing optional MrScraper proxy
            credentials and targeting values.

    Returns:
        HTTP proxy URL suitable for `httpx.AsyncClient(proxy=...)`, or `None`
        when MrScraper credentials are not configured.

    Raises:
        ValueError: If only one credential is provided or targeting values are
            malformed.

    Example:
        `MRSCRAPER_PROXY_USERNAME=user`, `MRSCRAPER_PROXY_PASSWORD=pass`, and
        `MRSCRAPER_PROXY_COUNTRY=us` produce
        `http://user-country-us:pass@proxy.mrscraper.com:10000`.
    """
    username = environ.get("MRSCRAPER_PROXY_USERNAME", "").strip()
    password = environ.get("MRSCRAPER_PROXY_PASSWORD", "").strip()
    if not username and not password:
        return None
    if not username or not password:
        raise ValueError("both MRSCRAPER_PROXY_USERNAME and MRSCRAPER_PROXY_PASSWORD are required")

    country = environ.get("MRSCRAPER_PROXY_COUNTRY", "").strip().lower()
    mobile = environ.get("MRSCRAPER_PROXY_MOBILE", "").strip().lower()
    session_id = environ.get("MRSCRAPER_PROXY_SESSION_ID", "").strip()
    session_minutes = environ.get("MRSCRAPER_PROXY_SESSION_MINUTES", "").strip()

    if country and (len(country) != 2 or not country.isalpha()):
        raise ValueError("MRSCRAPER_PROXY_COUNTRY must be a two-letter ISO country code")
    if mobile and mobile not in {"1", "true", "yes", "on"}:
        raise ValueError("MRSCRAPER_PROXY_MOBILE must be true-like when set")
    if session_id and not session_id.replace("_", "").isalnum():
        raise ValueError("MRSCRAPER_PROXY_SESSION_ID must be alphanumeric or underscores")

    proxy_username = username
    if country:
        proxy_username += "-mobile" if mobile else ""
        proxy_username += f"-country-{country}"
    elif mobile:
        raise ValueError("MRSCRAPER_PROXY_MOBILE requires MRSCRAPER_PROXY_COUNTRY")

    if session_id:
        if not country:
            raise ValueError("MRSCRAPER_PROXY_SESSION_ID requires MRSCRAPER_PROXY_COUNTRY")
        proxy_username += f"-sessid-{session_id}"
    if session_minutes:
        if not session_id:
            raise ValueError("MRSCRAPER_PROXY_SESSION_MINUTES requires MRSCRAPER_PROXY_SESSION_ID")
        try:
            minutes = int(session_minutes)
        except ValueError as error:
            raise ValueError("MRSCRAPER_PROXY_SESSION_MINUTES must be an integer") from error
        if minutes <= 0:
            raise ValueError("MRSCRAPER_PROXY_SESSION_MINUTES must be positive")
        proxy_username += f"-sesstime-{minutes}"

    return (
        "http://"
        f"{quote(proxy_username, safe='-_')}:"
        f"{quote(password, safe='')}"
        "@proxy.mrscraper.com:10000"
    )


def parse_settings(environ: dict[str, str]) -> Settings:
    """Parse settings from an environment mapping.

    Args:
        environ: Environment-style mapping, usually `os.environ`.

    Returns:
        Parsed settings.

    Raises:
        ValidationError: If environment values cannot be parsed into settings.
        ValueError: If MrScraper proxy credential settings are incomplete or malformed.
    """
    proxy_url = environ.get("PROXY_URL") or build_mrscraper_proxy_url(environ)
    return Settings(
        google_base_url=environ.get("GOOGLE_BASE_URL", Settings().google_base_url),
        mrscraper_api_key=environ.get("MRSCRAPER_API_KEY") or None,
        mrscraper_api_url=environ.get(
            "MRSCRAPER_API_URL",
            Settings().mrscraper_api_url,
        ),
        request_timeout_seconds=environ.get(
            "REQUEST_TIMEOUT_SECONDS",
            str(Settings().request_timeout_seconds),
        ),
        max_concurrency=environ.get("MAX_CONCURRENCY", str(Settings().max_concurrency)),
        user_agent=environ.get("USER_AGENT", Settings().user_agent),
        proxy_url=proxy_url,
    )


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse a local dotenv-style file into environment values.

    Args:
        path: File path containing `KEY=value` lines.

    Returns:
        Parsed environment values. Missing files return an empty mapping.

    Notes:
        This parser intentionally supports only the simple dotenv subset used by
        this project: comments, blank lines, optional `export`, whitespace
        around `=`, and single- or double-quoted values.
    """
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed_key = key.strip()
        parsed_value = value.strip()
        if (
            len(parsed_value) >= 2
            and parsed_value[0] == parsed_value[-1]
            and parsed_value[0] in {"'", '"'}
        ):
            parsed_value = parsed_value[1:-1]
        if parsed_key:
            values[parsed_key] = parsed_value
    return values


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached process settings.

    Returns:
        Settings parsed from `os.environ`.

    Raises:
        ValidationError: If process environment values are invalid.
    """
    try:
        merged_environ = {**parse_env_file(Path(".env")), **os.environ}
        return parse_settings(merged_environ)
    except ValidationError:
        raise
