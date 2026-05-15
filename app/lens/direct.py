"""Direct Google Lens request client.

This module intentionally contains no browser automation fallback. The hard
challenge work is isolated here: build the correct direct Exact Match request,
send it with realistic headers and proxy configuration, and return the raw HTML
for classification.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

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
        mrscraper_api_key: Optional MrScraper Scraper API token. When present,
            upstream Google Lens requests are fetched through the MrScraper API
            with `html=true` and `super=true`.
        mrscraper_api_url: MrScraper Scraper API endpoint.
        timeout_seconds: Per-request timeout.
        user_agent: User agent header.
        proxy_url: Optional outbound proxy URL.
    """

    google_base_url: str
    timeout_seconds: float
    user_agent: str
    mrscraper_api_key: str | None = None
    mrscraper_api_url: str = "https://api.mrscraper.com"
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

    def build_mrscraper_api_url(self, target_url: str) -> str:
        """Build a MrScraper API request URL for a target page.

        Args:
            target_url: Fully formed target URL that MrScraper should fetch.

        Returns:
            MrScraper Scraper API request URL.

        Raises:
            ValueError: If this client was not configured with a MrScraper API
                key.
        """
        if self.mrscraper_api_key is None:
            raise ValueError("mrscraper_api_key is required")
        query = urlencode(
            {
                "token": self.mrscraper_api_key,
                "html": "true",
                "super": "true",
                "url": target_url,
            }
        )
        return f"{self.mrscraper_api_url}?{query}"

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
        import httpx

        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.9",
            "user-agent": self.user_agent,
        }
        upstream_url = self.build_exact_match_url(image_url)
        request_url = upstream_url
        if self.mrscraper_api_key is not None:
            request_url = self.build_mrscraper_api_url(upstream_url)
            headers["x-api-token"] = self.mrscraper_api_key

        timeout = httpx.Timeout(self.timeout_seconds)
        proxy = self.proxy_url if self.proxy_url else None

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                headers=headers,
                proxy=proxy,
                timeout=timeout,
            ) as client:
                response = await client.get(request_url)
        except httpx.TimeoutException as error:
            raise UpstreamTimeoutError("Google Lens request timed out") from error
        except httpx.HTTPError as error:
            raise UpstreamRequestError("Google Lens request failed") from error

        return DirectLensResponse(
            html=response.text,
            final_url=upstream_url if self.mrscraper_api_key is not None else str(response.url),
            status_code=response.status_code,
        )
