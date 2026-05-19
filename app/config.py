"""Application configuration parsing.

Configuration is parsed at process boundary from environment variables and
stored as a typed value before it reaches request handling code.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

DEFAULT_GOOGLE_BASE_URL = "https://lens.google.com/uploadbyurl"
DEFAULT_MRSCRAPER_API_URL = "https://api.mrscraper.com"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_CONCURRENCY = 16
DEFAULT_REQUEST_DELAY_MIN_SECONDS = 0.0
DEFAULT_REQUEST_DELAY_MAX_SECONDS = 0.25
DEFAULT_MRSCRAPER_BLOCK_RESOURCES = False
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


class Settings(BaseModel):
    """Runtime settings for the Google Lens API.

    Attributes:
        google_base_url: Base Google Lens upload-by-URL endpoint submitted to
            MrScraper for fetching.
        request_timeout_seconds: Upstream request timeout in seconds.
        max_concurrency: Maximum in-process concurrent upstream requests.
        request_delay_min_seconds: Minimum randomized delay before upstream requests.
        request_delay_max_seconds: Maximum randomized delay before upstream requests.
        user_agent: User agent sent to Google.
        mrscraper_api_key: Required MrScraper Scraper API token.
        mrscraper_api_url: MrScraper Scraper API endpoint.
        mrscraper_block_resources: Optional provider hint to block images,
            CSS, and fonts while rendering upstream HTML. Disabled by default
            because the measured Lens path was slower with it enabled.
        log_level: Minimum application log level. Set LOG_LEVEL=DEBUG for
            local diagnostics; keep production at INFO or higher.

    Example:
        >>> settings = Settings(mrscraper_api_key="token")
        >>> settings.google_base_url
        'https://lens.google.com/uploadbyurl'
    """

    google_base_url: str = Field(default=DEFAULT_GOOGLE_BASE_URL)
    log_level: str = Field(default=DEFAULT_LOG_LEVEL)
    request_timeout_seconds: float = Field(default=DEFAULT_REQUEST_TIMEOUT_SECONDS, gt=0)
    max_concurrency: int = Field(default=DEFAULT_MAX_CONCURRENCY, gt=0)
    request_delay_min_seconds: float = Field(default=DEFAULT_REQUEST_DELAY_MIN_SECONDS, ge=0)
    request_delay_max_seconds: float = Field(default=DEFAULT_REQUEST_DELAY_MAX_SECONDS, ge=0)
    user_agent: str = Field(default=DEFAULT_USER_AGENT, min_length=1)
    mrscraper_api_key: str
    mrscraper_api_url: str = Field(default=DEFAULT_MRSCRAPER_API_URL)
    mrscraper_block_resources: bool = Field(default=DEFAULT_MRSCRAPER_BLOCK_RESOURCES)

    @field_validator("log_level")
    @classmethod
    def parse_log_level(cls, value: str) -> str:
        """Parse and constrain the configured application log level.

        Args:
            value: Candidate log level name.

        Returns:
            Uppercase log level name.

        Raises:
            ValueError: If the level is not one of Python standard levels.

        Example:
            >>> Settings.parse_log_level(" debug ")
            'DEBUG'
        """
        normalized = value.strip().upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(
                "LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL"
            )
        return normalized

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

        Example:
            >>> Settings.require_https_google_url("https://lens.google.com/uploadbyurl?")
            'https://lens.google.com/uploadbyurl'
        """
        if not value.startswith("https://"):
            raise ValueError("google_base_url must be an HTTPS URL")
        return value.rstrip("?")

    @field_validator("mrscraper_api_key")
    @classmethod
    def require_mrscraper_api_key(cls, value: str) -> str:
        """Parse and require the MrScraper API token.

        Args:
            value: Candidate MrScraper API token.

        Returns:
            Stripped API token.

        Raises:
            ValueError: If the token is empty.

        Example:
            >>> Settings.require_mrscraper_api_key(" token ")
            'token'
        """
        stripped = value.strip()
        if not stripped:
            raise ValueError("MRSCRAPER_API_KEY is required")
        return stripped

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

        Example:
            >>> Settings.require_https_mrscraper_api_url("https://api.mrscraper.com?")
            'https://api.mrscraper.com'
        """
        stripped = value.strip()
        if not stripped.startswith("https://"):
            raise ValueError("mrscraper_api_url must be an HTTPS URL")
        return stripped.rstrip("?")

    @model_validator(mode="after")
    def require_valid_delay_range(self) -> "Settings":
        """Ensure randomized request delay settings form a valid range.

        Returns:
            Parsed settings.

        Raises:
            ValueError: If the maximum delay is lower than the minimum delay.

        Example:
            >>> settings = Settings(mrscraper_api_key="token", request_delay_min_seconds=0.1, request_delay_max_seconds=0.1)
            >>> settings.require_valid_delay_range() is settings
            True
        """
        if self.request_delay_max_seconds < self.request_delay_min_seconds:
            raise ValueError(
                "REQUEST_DELAY_MAX_SECONDS must be greater than or equal to "
                "REQUEST_DELAY_MIN_SECONDS"
            )
        return self


def parse_settings(environ: dict[str, str]) -> Settings:
    """Parse settings from an environment mapping.

    Args:
        environ: Environment-style mapping, usually `os.environ`.

    Returns:
        Parsed settings.

    Raises:
        ValidationError: If environment values cannot be parsed into settings.

    Example:
        >>> parse_settings({"MRSCRAPER_API_KEY": " token "}).mrscraper_api_key
        'token'
    """
    return Settings(
        google_base_url=environ.get("GOOGLE_BASE_URL", DEFAULT_GOOGLE_BASE_URL),
        log_level=environ.get("LOG_LEVEL", DEFAULT_LOG_LEVEL),
        mrscraper_api_key=environ.get("MRSCRAPER_API_KEY", ""),
        mrscraper_api_url=environ.get(
            "MRSCRAPER_API_URL",
            DEFAULT_MRSCRAPER_API_URL,
        ),
        request_timeout_seconds=environ.get(
            "REQUEST_TIMEOUT_SECONDS",
            str(DEFAULT_REQUEST_TIMEOUT_SECONDS),
        ),
        max_concurrency=environ.get("MAX_CONCURRENCY", str(DEFAULT_MAX_CONCURRENCY)),
        request_delay_min_seconds=environ.get(
            "REQUEST_DELAY_MIN_SECONDS",
            str(DEFAULT_REQUEST_DELAY_MIN_SECONDS),
        ),
        request_delay_max_seconds=environ.get(
            "REQUEST_DELAY_MAX_SECONDS",
            str(DEFAULT_REQUEST_DELAY_MAX_SECONDS),
        ),
        user_agent=environ.get("USER_AGENT", DEFAULT_USER_AGENT),
        mrscraper_block_resources=environ.get(
            "MRSCRAPER_BLOCK_RESOURCES",
            str(DEFAULT_MRSCRAPER_BLOCK_RESOURCES),
        ),
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

    Example:
        >>> from pathlib import Path
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmp:
        ...     path = Path(tmp) / ".env"
        ...     _ = path.write_text("export MRSCRAPER_API_KEY='token'\\n", encoding="utf-8")
        ...     parse_env_file(path)
        {'MRSCRAPER_API_KEY': 'token'}
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


def get_settings() -> Settings:
    """Return parsed process settings.

    Returns:
        Settings parsed from `os.environ`.

    Raises:
        ValidationError: If process environment values are invalid.

    Example:
        >>> parse_settings({"MRSCRAPER_API_KEY": "token"}).mrscraper_api_key
        'token'
    """
    try:
        merged_environ = {**parse_env_file(Path(".env")), **os.environ}
        return parse_settings(merged_environ)
    except ValidationError:
        raise
