"""Direct Google Lens request client.

This module intentionally contains no browser automation fallback. The hard
challenge work is isolated here: build the correct direct Exact Match request,
send it with realistic headers and proxy configuration, and return the raw HTML
for classification.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.errors import UpstreamRequestError, UpstreamTimeoutError
from app.models import ImageUrl


@dataclass(frozen=True)
class DirectLensResponse:
    """Raw direct Google response before HTML classification.

    Attributes:
        html: Upstream response body.
        final_url: Final URL after redirects.
        status_code: Upstream HTTP status code.
    """

    html: str
    final_url: str
    status_code: int


@dataclass(frozen=True)
class DirectLensClient:
    """HTTP client for the direct Google Lens Exact Match request path.

    Args:
        google_base_url: Base Google Lens upload-by-URL endpoint.
        timeout_seconds: Per-request timeout.
        user_agent: User agent header.
        proxy_url: Optional outbound proxy URL.
    """

    google_base_url: str
    timeout_seconds: float
    user_agent: str
    proxy_url: str | None = None

    def build_exact_match_url(self, image_url: ImageUrl) -> str:
        """Build the direct upstream request URL for an image.

        Args:
            image_url: Parsed image URL from the API boundary.

        Returns:
            Google Lens upload-by-URL request.

        Notes:
            The parameter set is intentionally centralized here so live
            reverse-engineering can refine it without changing route or service
            code.
        """
        query = urlencode(
            {
                "url": image_url.value,
                "hl": "en",
                "gl": "US",
            }
        )
        return f"{self.google_base_url}?{query}"

    async def fetch_exact_match_html(self, image_url: ImageUrl) -> DirectLensResponse:
        """Fetch raw upstream HTML for the direct Exact Match path.

        Args:
            image_url: Parsed image URL to submit upstream.

        Returns:
            Raw upstream response details.

        Raises:
            UpstreamTimeoutError: If the upstream request times out.
            UpstreamRequestError: If the upstream request fails.
        """
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.9",
            "user-agent": self.user_agent,
        }
        timeout = httpx.Timeout(self.timeout_seconds)
        proxy = self.proxy_url if self.proxy_url else None

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                headers=headers,
                proxy=proxy,
                timeout=timeout,
            ) as client:
                response = await client.get(self.build_exact_match_url(image_url))
        except httpx.TimeoutException as error:
            raise UpstreamTimeoutError("Google Lens request timed out") from error
        except httpx.HTTPError as error:
            raise UpstreamRequestError("Google Lens request failed") from error

        return DirectLensResponse(
            html=response.text,
            final_url=str(response.url),
            status_code=response.status_code,
        )
