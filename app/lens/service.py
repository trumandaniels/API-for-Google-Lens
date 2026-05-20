"""Service orchestration for direct Google Lens Exact Match requests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import random

from app.config import Settings
from app.errors import (
    BotBlockError,
    ExactMatchNotFoundError,
    GoogleErrorPageError,
    ProviderCreditsExhaustedError,
    UpstreamRequestError,
)
from app.lens.classifier import HtmlVerdict, classify_google_html
from app.lens.direct import DirectLensClient
from app.models import ExactMatchHtml, ImageUrl, ProviderApiToken
from app.throttling import AsyncConcurrencyLimiter


PROVIDER_CREDIT_ERROR_DETAIL = (
    "Out of MrScraper credits. Create a free account at MrScraper.com, then "
    "pass your API key in the X-MrScraper-Api-Key header."
)
PROVIDER_RATE_LIMIT_DETAIL = "Provider or Google rate limited the request"
PROVIDER_CREDIT_ERROR_MARKERS = (
    "out of proxy credits",
    "proxy credits",
    "insufficient credits",
    "not enough credits",
)


def is_provider_credit_error(status_code: int, html: str) -> bool:
    """Return whether a provider response indicates exhausted proxy credits.

    Args:
        status_code: Upstream HTTP status code returned by the provider.
        html: Upstream response body returned by the scraping provider.

    Returns:
        `True` when the body contains a known credit-exhaustion marker.

    Example:
        >>> is_provider_credit_error(402, "")
        True
        >>> is_provider_credit_error(200, "out of proxy credits")
        True
    """

    if status_code == 402:
        return True

    normalized = html.lower()
    return any(marker in normalized for marker in PROVIDER_CREDIT_ERROR_MARKERS)


@dataclass(frozen=True)
class GoogleLensService:
    """Coordinate direct fetching, throttling, and response classification.

    Args:
        client: Direct Google request client.
        limiter: Concurrency limiter for upstream calls.
        request_delay_min_seconds: Minimum randomized delay before provider calls.
        request_delay_max_seconds: Maximum randomized delay before provider calls.

    Example:
        >>> service = GoogleLensService(client=object(), limiter=AsyncConcurrencyLimiter(1))
        >>> service.request_delay_max_seconds
        0.0
    """

    client: DirectLensClient
    limiter: AsyncConcurrencyLimiter
    request_delay_min_seconds: float = 0.0
    request_delay_max_seconds: float = 0.0

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        limiter: AsyncConcurrencyLimiter,
        http_client: object | None = None,
    ) -> "GoogleLensService":
        """Create a service from parsed application settings.

        Args:
            settings: Parsed runtime settings.
            limiter: Concurrency limiter for upstream requests.
            http_client: Optional process-scoped HTTP client for provider
                requests.

        Returns:
            Configured GoogleLensService.

        Example:
            >>> settings = Settings(mrscraper_api_key="token")
            >>> service = GoogleLensService.from_settings(settings, AsyncConcurrencyLimiter(1))
            >>> service.client.mrscraper_api_key
            'token'
        """
        client = DirectLensClient(
            google_base_url=settings.google_base_url,
            mrscraper_api_key=settings.mrscraper_api_key,
            mrscraper_api_url=settings.mrscraper_api_url,
            timeout_seconds=settings.request_timeout_seconds,
            user_agent=settings.user_agent,
            block_resources=settings.mrscraper_block_resources,
            http_client=http_client,
        )
        return cls(
            client=client,
            limiter=limiter,
            request_delay_min_seconds=settings.request_delay_min_seconds,
            request_delay_max_seconds=settings.request_delay_max_seconds,
        )

    async def wait_before_upstream_request(self) -> None:
        """Apply local randomized pacing before sending a provider request.

        The provider-side rotation layer is still responsible for Google-facing
        anti-bot behavior. This local delay reduces avoidable burstiness from
        the API process itself.

        Example:
            >>> import asyncio
            >>> service = GoogleLensService(client=object(), limiter=AsyncConcurrencyLimiter(1))
            >>> asyncio.run(service.wait_before_upstream_request()) is None
            True
        """
        if self.request_delay_max_seconds <= 0:
            return
        delay = random.uniform(
            self.request_delay_min_seconds,
            self.request_delay_max_seconds,
        )
        if delay > 0:
            await asyncio.sleep(delay)

    async def aclose(self) -> None:
        """Close owned network resources for application shutdown.

        Example:
            >>> import asyncio
            >>> class FakeClient:
            ...     closed = False
            ...     async def aclose(self):
            ...         self.closed = True
            >>> fake = FakeClient()
            >>> service = GoogleLensService(client=fake, limiter=AsyncConcurrencyLimiter(1))
            >>> asyncio.run(service.aclose())
            >>> fake.closed
            True
        """
        close = getattr(self.client, "aclose", None)
        if close is not None:
            await close()

    async def fetch_exact_match_html(
        self,
        image_url: ImageUrl,
        token_override: ProviderApiToken | None = None,
    ) -> ExactMatchHtml:
        """Fetch and classify Exact Match HTML for an image URL.

        Args:
            image_url: Parsed image URL from the API boundary.
            token_override: Optional per-request provider token supplied by the
                API caller.

        Returns:
            Raw Exact Match HTML and source URL.

        Raises:
            UpstreamRequestError: If Google returns a non-success HTTP status.
            ProviderCreditsExhaustedError: If the provider token has run out
                of proxy credits.
            BotBlockError: If the response appears to be CAPTCHA or bot-check HTML.
            GoogleErrorPageError: If the response appears to be a Google error page.
            ExactMatchNotFoundError: If the response cannot be classified as Exact
                Match HTML.

        Example:
            >>> import asyncio
            >>> from app.lens.direct import DirectLensResponse
            >>> class FakeClient:
            ...     async def fetch_exact_match_html(self, image_url, token_override=None):
            ...         return DirectLensResponse("<html>Exact matches Search Results</html>", "https://www.google.com/search?udm=48", 200)
            >>> service = GoogleLensService(client=FakeClient(), limiter=AsyncConcurrencyLimiter(1))
            >>> result = asyncio.run(service.fetch_exact_match_html(ImageUrl.parse("https://example.com/a.jpg")))
            >>> result.source_url
            'https://www.google.com/search?udm=48'
        """
        async with self.limiter.slot():
            await self.wait_before_upstream_request()
            response = await self.client.fetch_exact_match_html(image_url, token_override)

        if is_provider_credit_error(response.status_code, response.html):
            raise ProviderCreditsExhaustedError(PROVIDER_CREDIT_ERROR_DETAIL)
        if response.status_code == 429:
            raise BotBlockError(PROVIDER_RATE_LIMIT_DETAIL)
        if response.status_code >= 500:
            raise UpstreamRequestError(
                f"Provider or Google returned HTTP {response.status_code}"
            )
        if response.status_code >= 400:
            raise UpstreamRequestError(
                f"Provider or Google returned HTTP {response.status_code}"
            )

        classification = classify_google_html(response.html, response.final_url)
        if classification.verdict == HtmlVerdict.EXACT_MATCH:
            return ExactMatchHtml(html=response.html, source_url=response.final_url)
        if classification.verdict == HtmlVerdict.BOT_BLOCK:
            raise BotBlockError("Google returned CAPTCHA or bot-check HTML")
        if classification.verdict == HtmlVerdict.GOOGLE_ERROR:
            raise GoogleErrorPageError("Google returned an error page")
        if classification.verdict == HtmlVerdict.NO_MATCH:
            raise ExactMatchNotFoundError("Google Exact Match page contained no matches")

        raise ExactMatchNotFoundError("Google response was not Exact Match HTML")
