"""Direct Google Lens request client.

This module intentionally contains no browser automation fallback. The hard
challenge work is isolated here: build the correct direct Exact Match request,
send it with realistic headers and proxy configuration, and return the raw HTML
for classification.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import re
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
            `True` when an API token is configured. The API-token fetcher is a
            distinct provider path from the residential proxy product and takes
            precedence because residential proxy credentials may be present but
            unavailable or unentitled for the account.
        """
        return self.mrscraper_api_key is not None

    def build_lens_entry_url(self, image_url: ImageUrl) -> str:
        """Build the direct Google Lens entry URL for an image.

        Args:
            image_url: Parsed image URL from the API boundary.

        Returns:
            Google Lens upload-by-URL request that redirects to the Lens Search
            result page.

        Notes:
            Google currently redirects this minimal request to a
            `google.com/search` page with `udm=26`. Adding `hl`, `gl`, or `udm`
            to the Lens entry URL caused Google 403 responses during live
            provider verification, so those values are left for the redirected
            Search URL instead.
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
        final_url = upstream_url
        request_url = upstream_url
        if self.uses_mrscraper_api:
            request_url = self.build_mrscraper_api_url(upstream_url)
            headers["x-api-token"] = self.mrscraper_api_key or ""

        timeout = httpx.Timeout(self.timeout_seconds)
        proxy = self.proxy_url if self.proxy_url and not self.uses_mrscraper_api else None

        async def get(url: str, request_headers: dict[str, str]) -> httpx.Response:
            try:
                async with httpx.AsyncClient(
                    follow_redirects=True,
                    headers=request_headers,
                    proxy=proxy,
                    timeout=timeout,
                    trust_env=False,
                ) as client:
                    return await client.get(url)
            except httpx.TimeoutException as error:
                raise UpstreamTimeoutError("Google Lens request timed out") from error
            except httpx.HTTPError as error:
                raise UpstreamRequestError("Google Lens request failed") from error

        response = await get(request_url, headers)
        if self.uses_mrscraper_api:
            exact_url = self.find_exact_match_tab_url(response.text)
            if exact_url is not None:
                final_url = exact_url
                response = await get(self.build_mrscraper_api_url(exact_url), headers)
        elif "udm=26" in str(response.url):
            exact_url = self.build_exact_match_tab_url(str(response.url))
            exact_headers = {**headers, "referer": str(response.url)}
            final_url = exact_url
            response = await get(exact_url, exact_headers)
        else:
            final_url = str(response.url)

        return DirectLensResponse(
            html=response.text,
            final_url=final_url,
            status_code=response.status_code,
        )
