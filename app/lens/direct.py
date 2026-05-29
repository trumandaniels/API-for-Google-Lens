"""MrScraper-backed Google Lens request client.

This module intentionally contains no browser automation fallback. It builds
the Google Lens URL flow and always asks MrScraper's API-token HTML fetcher to
retrieve the upstream Google pages for classification.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import re
import time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from app.errors import UpstreamRequestError, UpstreamTimeoutError
from app.models import ImageUrl, ProviderApiToken
from app.observability import get_api_logger

LOGGER = get_api_logger()


@dataclass(frozen=True)
class DirectLensResponse:
    """Raw direct Google response before HTML classification.

    Attributes:
        html: Upstream response body returned by the final provider hop.
        final_url: Google URL represented by the final provider hop.
        status_code: Upstream HTTP status code.
        entry_html: Optional first-hop Lens results page retained for
            diagnostics; the service still returns the Exact Match hop.
        entry_url: Optional Google Lens entry URL used for the first hop.

    Example:
        >>> DirectLensResponse("<html></html>", "https://www.google.com/search?udm=48", 200).status_code
        200
    """

    html: str
    final_url: str
    status_code: int
    entry_html: str | None = None
    entry_url: str | None = None


@dataclass(frozen=True)
class DirectLensClient:
    """HTTP client for the direct Google Lens Exact Match request path.

    Args:
        google_base_url: Base Google Lens upload-by-URL endpoint.
        mrscraper_api_key: Required MrScraper Scraper API token.
        mrscraper_api_url: MrScraper Scraper API endpoint.
        timeout_seconds: Per-request timeout.
        user_agent: User agent header.
        block_resources: Optional provider hint to block images, CSS, and
            fonts while rendering the target page.

    Example:
        >>> client = DirectLensClient(
        ...     google_base_url="https://lens.google.com/uploadbyurl",
        ...     timeout_seconds=10,
        ...     user_agent="test-agent",
        ...     mrscraper_api_key="token",
        ... )
        >>> client.mrscraper_api_url
        'https://api.mrscraper.com'
    """

    google_base_url: str
    timeout_seconds: float
    user_agent: str
    mrscraper_api_key: str
    mrscraper_api_url: str = "https://api.mrscraper.com"
    block_resources: bool = False
    http_client: Any | None = None

    def resolve_mrscraper_api_key(self, token_override: ProviderApiToken | None = None) -> str:
        """Return the provider token to use for one upstream fetch.

        Args:
            token_override: Optional per-request provider token supplied by the
                API caller.

        Returns:
            The caller-supplied token when present, otherwise the configured
            process token.

        Example:
            >>> client = DirectLensClient("https://lens.google.com/uploadbyurl", 10, "ua", "default")
            >>> client.resolve_mrscraper_api_key(ProviderApiToken("override"))
            'override'
        """
        if token_override is not None:
            return token_override.value
        return self.mrscraper_api_key

    def build_request_headers(
        self,
        token_override: ProviderApiToken | None = None,
    ) -> dict[str, str]:
        """Build stable headers for MrScraper-backed Google page fetches.

        Args:
            token_override: Optional per-request provider token supplied by the
                API caller.

        Returns:
            Browser-like request headers. The API token is included both in the
            MrScraper query string and the provider token header accepted by
            the service.

        Example:
            >>> client = DirectLensClient("https://lens.google.com/uploadbyurl", 10, "ua", "token")
            >>> client.build_request_headers()["x-api-token"]
            'token'
        """
        api_key = self.resolve_mrscraper_api_key(token_override)
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
            "x-api-token": api_key,
        }

    async def aclose(self) -> None:
        """Close the owned process-scoped HTTP client, if one was provided.

        Example:
            >>> import asyncio
            >>> class FakeHttpClient:
            ...     closed = False
            ...     async def aclose(self):
            ...         self.closed = True
            >>> fake = FakeHttpClient()
            >>> client = DirectLensClient("https://lens.google.com/uploadbyurl", 10, "ua", "token", http_client=fake)
            >>> asyncio.run(client.aclose())
            >>> fake.closed
            True
        """
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

        Example:
            >>> client = DirectLensClient("https://lens.google.com/uploadbyurl", 10, "ua", "token")
            >>> client.build_lens_entry_url(ImageUrl.parse("https://example.com/a.jpg"))
            'https://lens.google.com/uploadbyurl?url=https%3A%2F%2Fexample.com%2Fa.jpg'
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

        Example:
            >>> client = DirectLensClient("https://lens.google.com/uploadbyurl", 10, "ua", "token")
            >>> client.build_exact_match_url(ImageUrl.parse("https://example.com/a.jpg")).startswith("https://lens.google.com/uploadbyurl?")
            True
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

        Example:
            >>> client = DirectLensClient("https://lens.google.com/uploadbyurl", 10, "ua", "token")
            >>> client.build_exact_match_tab_url("https://www.google.com/search?q=x&udm=26")
            'https://www.google.com/search?q=x&udm=48'
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

        Example:
            >>> client = DirectLensClient("https://lens.google.com/uploadbyurl", 10, "ua", "token")
            >>> html = '<a href="/search?q=shirt&amp;udm=48">Exact matches</a>'
            >>> client.find_exact_match_tab_url(html)
            'https://www.google.com/search?q=shirt&udm=48'
        """
        match = re.search(
            r'href="(?P<href>[^"]*?(?:[?&]|&amp;)udm=48[^"]*?)"',
            html,
            re.DOTALL,
        )
        if match is None:
            return None
        return urljoin("https://www.google.com", unescape(match.group("href")))

    def build_mrscraper_api_url(
        self,
        target_url: str,
        token_override: ProviderApiToken | None = None,
    ) -> str:
        """Build a MrScraper API request URL for a target page.

        Args:
            target_url: Fully formed target URL that MrScraper should fetch.
            token_override: Optional per-request provider token supplied by the
                API caller.

        Returns:
            MrScraper HTML fetch request URL.

        Raises:
            ValueError: If this client was not configured with a MrScraper API
                key.

        Example:
            >>> client = DirectLensClient("https://lens.google.com/uploadbyurl", 10, "ua", "token")
            >>> url = client.build_mrscraper_api_url("https://www.google.com/search?udm=48")
            >>> "html=true" in url and "url=https%3A%2F%2Fwww.google.com" in url
            True
        """
        api_key = self.resolve_mrscraper_api_key(token_override)
        if not api_key:
            raise ValueError("mrscraper_api_key is required")
        query_params = {
            "token": api_key,
            "html": "true",
            "super": "true",
            "url": target_url,
        }
        if self.block_resources:
            query_params["blockResources"] = "true"
        query = urlencode(query_params)
        return f"{self.mrscraper_api_url}?{query}"

    async def fetch_exact_match_html(
        self,
        image_url: ImageUrl,
        token_override: ProviderApiToken | None = None,
    ) -> DirectLensResponse:
        """Fetch raw upstream HTML for the direct Exact Match path.

        Args:
            image_url: Parsed image URL to submit upstream.
            token_override: Optional per-request provider token supplied by the
                API caller.

        Returns:
            Raw upstream response details.

        Raises:
            UpstreamTimeoutError: If the upstream request times out.
            UpstreamRequestError: If the upstream request fails.

        Example:
            >>> import asyncio
            >>> class FakeResponse:
            ...     status_code = 200
            ...     text = "<html>Exact matches Search Results</html>"
            ...     content = text.encode("utf-8")
            ...     http_version = "HTTP/1.1"
            >>> class FakeHttpClient:
            ...     async def get(self, url, headers):
            ...         return FakeResponse()
            >>> client = DirectLensClient(
            ...     "https://lens.google.com/uploadbyurl",
            ...     10,
            ...     "ua",
            ...     "token",
            ...     http_client=FakeHttpClient(),
            ... )
            >>> result = asyncio.run(client.fetch_exact_match_html(ImageUrl.parse("https://example.com/a.jpg")))
            >>> result.status_code
            200
        """
        import httpx

        headers = self.build_request_headers(token_override)
        upstream_url = self.build_exact_match_url(image_url)
        final_url = upstream_url
        request_url = self.build_mrscraper_api_url(upstream_url, token_override)

        timeout = httpx.Timeout(self.timeout_seconds)

        async def get(
            url: str,
            request_headers: dict[str, str],
            hop_name: str,
        ) -> httpx.Response:
            started = time.perf_counter()
            try:
                if self.http_client is not None:
                    response = await self.http_client.get(url, headers=request_headers)
                else:
                    async with httpx.AsyncClient(
                        follow_redirects=True,
                        timeout=timeout,
                        trust_env=False,
                    ) as client:
                        response = await client.get(url, headers=request_headers)
                LOGGER.debug(
                    "lens_provider_hop hop=%s status=%s elapsed_ms=%.0f "
                    "bytes=%s http_version=%s",
                    hop_name,
                    response.status_code,
                    (time.perf_counter() - started) * 1000,
                    len(response.content),
                    response.http_version,
                )
                return response
            except httpx.TimeoutException as error:
                elapsed_ms = (time.perf_counter() - started) * 1000
                LOGGER.warning(
                    "lens_provider_hop_timeout hop=%s elapsed_ms=%.0f "
                    "timeout_seconds=%.1f",
                    hop_name,
                    elapsed_ms,
                    self.timeout_seconds,
                )
                raise UpstreamTimeoutError(
                    f"Google Lens {hop_name} request timed out"
                ) from error
            except httpx.HTTPError as error:
                raise UpstreamRequestError("Google Lens request failed") from error

        response = await get(request_url, headers, "lens_entry")
        entry_html = response.text
        entry_url = upstream_url
        exact_url = self.find_exact_match_tab_url(response.text)
        if exact_url is not None:
            final_url = exact_url
            response = await get(
                self.build_mrscraper_api_url(exact_url, token_override),
                headers,
                "exact_match",
            )

        return DirectLensResponse(
            html=response.text,
            final_url=final_url,
            status_code=response.status_code,
            entry_html=entry_html,
            entry_url=entry_url,
        )
