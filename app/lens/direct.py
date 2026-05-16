"""MrScraper-backed Google Lens request client.

This module intentionally contains no browser automation fallback. It builds
the Google Lens URL flow and always asks MrScraper's API-token HTML fetcher to
retrieve the upstream Google pages for classification.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

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
        mrscraper_api_key: Required MrScraper Scraper API token.
        mrscraper_api_url: MrScraper Scraper API endpoint.
        timeout_seconds: Per-request timeout.
        user_agent: User agent header.
    """

    google_base_url: str
    timeout_seconds: float
    user_agent: str
    mrscraper_api_key: str
    mrscraper_api_url: str = "https://api.mrscraper.com"
    http_client: Any | None = None

    def build_request_headers(self) -> dict[str, str]:
        """Build stable headers for MrScraper-backed Google page fetches.

        Returns:
            Browser-like request headers. The API token is included both in the
            MrScraper query string and the provider token header accepted by
            the service.
        """
        return {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.9",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "user-agent": self.user_agent,
            "x-api-token": self.mrscraper_api_key,
        }

    async def aclose(self) -> None:
        """Close the owned process-scoped HTTP client, if one was provided."""
        if self.http_client is not None:
            await self.http_client.aclose()

    def build_lens_entry_url(self, image_url: ImageUrl) -> str:
        """Build the direct Google Lens entry URL for an image.

        Args:
            image_url: Parsed image URL from the API boundary.

        Returns:
            Google Lens upload-by-URL request that redirects to the Lens Search
            result page.

        Notes:
            MrScraper fetches this Google URL, which redirects to a
            `google.com/search` page with `udm=26`. Adding `hl`, `gl`, or `udm`
            to the Lens entry URL caused Google 403 responses during prior live
            verification, so the entry URL stays minimal.
        """
        query = urlencode(
            {
                "url": image_url.value,
            }
        )
        return f"{self.google_base_url}?{query}"

    def build_exact_match_url(self, image_url: ImageUrl) -> str:
        """Build the initial URL used to reach the Exact Match path.

        Args:
            image_url: Parsed image URL from the API boundary.

        Returns:
            Google Lens entry URL. Exact Match is reached after Google creates
            a Search session for this image.
        """
        return self.build_lens_entry_url(image_url)

    def build_exact_match_tab_url(self, search_url: str) -> str:
        """Convert a redirected Google Lens Search URL to Exact Match.

        Args:
            search_url: Final Google Search URL returned from the Lens entry
                request.

        Returns:
            Search URL with `udm=48`, Google's Exact Match tab parameter.
            Non-Google or non-query URLs are returned with the same path and
            query parameters except for the `udm` value.
        """
        parsed = urlparse(search_url)
        query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
        replaced = False
        updated_pairs: list[tuple[str, str]] = []
        for key, value in query_pairs:
            if key == "udm":
                updated_pairs.append((key, "48"))
                replaced = True
            else:
                updated_pairs.append((key, value))
        if not replaced:
            updated_pairs.append(("udm", "48"))
        return urlunparse(parsed._replace(query=urlencode(updated_pairs)))

    def find_exact_match_tab_url(self, html: str) -> str | None:
        """Extract the Exact Match tab URL from a Lens Search page.

        Args:
            html: Raw Google Lens Search HTML, usually the All tab.

        Returns:
            Absolute Google Search URL for the Exact Match tab, or `None` when
            the tab link is not present.
        """
        match = re.search(r'href="(?P<href>[^"]*?udm=48[^"]*?)"[^>]*>.*?Exact matches', html, re.DOTALL)
        if match is None:
            return None
        return urljoin("https://www.google.com", unescape(match.group("href")))

    def build_mrscraper_api_url(self, target_url: str) -> str:
        """Build a MrScraper API request URL for a target page.

        Args:
            target_url: Fully formed target URL that MrScraper should fetch.

        Returns:
            MrScraper HTML fetch request URL.

        Raises:
            ValueError: If this client was not configured with a MrScraper API
                key.
        """
        if not self.mrscraper_api_key:
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

        headers = self.build_request_headers()
        upstream_url = self.build_exact_match_url(image_url)
        final_url = upstream_url
        request_url = self.build_mrscraper_api_url(upstream_url)

        timeout = httpx.Timeout(self.timeout_seconds)

        async def get(url: str, request_headers: dict[str, str]) -> httpx.Response:
            try:
                if self.http_client is not None:
                    return await self.http_client.get(url, headers=request_headers)
                async with httpx.AsyncClient(
                    follow_redirects=True,
                    timeout=timeout,
                    trust_env=False,
                ) as client:
                    return await client.get(url, headers=request_headers)
            except httpx.TimeoutException as error:
                raise UpstreamTimeoutError("Google Lens request timed out") from error
            except httpx.HTTPError as error:
                raise UpstreamRequestError("Google Lens request failed") from error

        response = await get(request_url, headers)
        exact_url = self.find_exact_match_tab_url(response.text)
        if exact_url is not None:
            final_url = exact_url
            response = await get(self.build_mrscraper_api_url(exact_url), headers)

        return DirectLensResponse(
            html=response.text,
            final_url=final_url,
            status_code=response.status_code,
        )
