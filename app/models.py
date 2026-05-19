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

    Example:
        >>> image_url = ImageUrl.parse(" https://example.com/product.jpg ")
        >>> image_url.value
        'https://example.com/product.jpg'
        >>> image_url.parsed.netloc
        'example.com'
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

        Example:
            >>> ImageUrl.parse("http://example.com/a.png").parsed.scheme
            'http'
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
class ProviderApiToken:
    """Parsed per-request scraping-provider API token.

    Attributes:
        value: Stripped provider token supplied by a trusted API caller.

    Example:
        >>> ProviderApiToken.parse_optional("  token-123  ")
        ProviderApiToken(value='token-123')
    """

    value: str

    @classmethod
    def parse_optional(cls, raw_value: str | None) -> "ProviderApiToken | None":
        """Parse an optional provider token override.

        Args:
            raw_value: Optional token header value from the HTTP request.

        Returns:
            Parsed token when a non-empty value is supplied; otherwise `None`.

        Example:
            >>> ProviderApiToken.parse_optional("   ") is None
            True
        """
        if raw_value is None:
            return None
        value = raw_value.strip()
        if not value:
            return None
        return cls(value=value)


@dataclass(frozen=True)
class ExactMatchHtml:
    """Successful Google Lens Exact Match response.

    Attributes:
        html: Raw HTML body returned to the API client.
        source_url: Final upstream URL that produced the HTML.

    Example:
        >>> response = ExactMatchHtml("<html>Exact matches</html>", "https://www.google.com/search?udm=48")
        >>> response.source_url
        'https://www.google.com/search?udm=48'
    """

    html: str
    source_url: str
