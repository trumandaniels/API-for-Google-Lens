"""Typed boundary models for the Google Lens API."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import ParseResult, urlparse

from app.errors import MalformedImageUrlError


@dataclass(frozen=True)
class ImageUrl:
    """Parsed public image URL accepted by the API.

    Attributes:
        value: Normalized absolute HTTPS or HTTP URL string.
        parsed: Parsed URL components.
    """

    value: str
    parsed: ParseResult

    @classmethod
    def parse(cls, raw_value: str) -> "ImageUrl":
        """Parse a raw query parameter into a trusted image URL.

        Args:
            raw_value: Untrusted `imageUrl` query parameter value.

        Returns:
            Parsed image URL.

        Raises:
            MalformedImageUrlError: If the value is empty, relative, missing a
                host, or uses an unsupported scheme.
        """
        value = raw_value.strip()
        if not value:
            raise MalformedImageUrlError("imageUrl must not be empty")

        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"}:
            raise MalformedImageUrlError("imageUrl must use http or https")
        if not parsed.netloc:
            raise MalformedImageUrlError("imageUrl must include a host")

        return cls(value=value, parsed=parsed)


@dataclass(frozen=True)
class ExactMatchHtml:
    """Successful Google Lens Exact Match response.

    Attributes:
        html: Raw HTML body returned to the API client.
        source_url: Final upstream URL that produced the HTML.
    """

    html: str
    source_url: str

