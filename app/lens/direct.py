"""Direct Google Lens request client.

This module intentionally contains no browser automation fallback. The hard
challenge work is isolated here: build the correct direct Exact Match request,
send it with realistic headers and proxy configuration, and return the raw HTML
for classification.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

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

    @property
    def uses_mrscraper_api(self) -> bool:
        """Return whether requests should use MrScraper's HTML fetch API.

        Returns:
            `True` when an API token is configured and no direct proxy URL is
            available. A direct proxy URL takes precedence so residential proxy
            credentials can fetch Google itself instead of proxying a request to
            MrScraper's API endpoint.
        """
        return self.mrscraper_api_key is not None and self.proxy_url is None

    def build_exact_match_url(self, image_url: ImageUrl) -> str:
        """Build the direct Google Lens entry URL for an image.

        Args:
            image_url: Parsed image URL from the API boundary.

        Returns:
            Google Lens upload-by-URL request that redirects to the Lens Search
            result page.

        Notes:
            Google currently redirects this request to a `google.com/search`
            page with `udm=26`. The Exact Match tab is reached by changing that
            redirected Search URL to `udm=48`.
        """
        query = urlencode(
            {
                "url": image_url.value,
                "hl": "en",
                "gl": "US",
                "udm": "26",
            }
        )
        return f"{self.google_base_url}?{query}"

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
        if self.mrscraper_api_key is None:
            raise ValueError("mrscraper_api_key is required")
        query = urlencode(
            {
                "token": self.mrscraper_api_key,
                "timeout": str(int(self.timeout_seconds)),
                "geoCode": "US",
                "url": target_url,
                "blockResources": "false",
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
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "user-agent": self.user_agent,
        }
        upstream_url = self.build_exact_match_url(image_url)
        request_url = upstream_url
        if self.uses_mrscraper_api:
            request_url = self.build_mrscraper_api_url(upstream_url)

        timeout = httpx.Timeout(self.timeout_seconds)
        proxy = self.proxy_url if self.proxy_url else None

        async def get(url: str, request_headers: dict[str, str]) -> httpx.Response:
            try:
                async with httpx.AsyncClient(
                    follow_redirects=True,
                    headers=request_headers,
                    proxy=proxy,
                    timeout=timeout,
                ) as client:
                    return await client.get(url)
            except httpx.TimeoutException as error:
                raise UpstreamTimeoutError("Google Lens request timed out") from error
            except httpx.HTTPError as error:
                raise UpstreamRequestError("Google Lens request failed") from error

        response = await get(request_url, headers)
        if not self.uses_mrscraper_api and "udm=26" in str(response.url):
            exact_url = self.build_exact_match_tab_url(str(response.url))
            exact_headers = {**headers, "referer": str(response.url)}
            response = await get(exact_url, exact_headers)

        return DirectLensResponse(
            html=response.text,
            final_url=upstream_url if self.uses_mrscraper_api else str(response.url),
            status_code=response.status_code,
        )
