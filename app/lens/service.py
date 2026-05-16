"""Service orchestration for direct Google Lens Exact Match requests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import random

from app.config import Settings
from app.errors import BotBlockError, ExactMatchNotFoundError, GoogleErrorPageError, UpstreamRequestError
from app.lens.classifier import HtmlVerdict, classify_google_html
from app.lens.direct import DirectLensClient
from app.models import ExactMatchHtml, ImageUrl
from app.throttling import AsyncConcurrencyLimiter


@dataclass(frozen=True)
class GoogleLensService:
    """Coordinate direct fetching, throttling, and response classification.

    Args:
        client: Direct Google request client.
        limiter: Concurrency limiter for upstream calls.
        request_delay_min_seconds: Minimum randomized delay before provider calls.
        request_delay_max_seconds: Maximum randomized delay before provider calls.
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
    ) -> "GoogleLensService":
        """Create a service from parsed application settings.

        Args:
            settings: Parsed runtime settings.
            limiter: Concurrency limiter for upstream requests.

        Returns:
            Configured GoogleLensService.
        """
        client = DirectLensClient(
            google_base_url=settings.google_base_url,
            mrscraper_api_key=settings.mrscraper_api_key,
            mrscraper_api_url=settings.mrscraper_api_url,
            timeout_seconds=settings.request_timeout_seconds,
            user_agent=settings.user_agent,
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
        """
        if self.request_delay_max_seconds <= 0:
            return
        delay = random.uniform(
            self.request_delay_min_seconds,
            self.request_delay_max_seconds,
        )
        if delay > 0:
            await asyncio.sleep(delay)

    async def fetch_exact_match_html(self, image_url: ImageUrl) -> ExactMatchHtml:
        """Fetch and classify Exact Match HTML for an image URL.

        Args:
            image_url: Parsed image URL from the API boundary.

        Returns:
            Raw Exact Match HTML and source URL.

        Raises:
            UpstreamRequestError: If Google returns a non-success HTTP status.
            BotBlockError: If the response appears to be CAPTCHA or bot-check HTML.
            GoogleErrorPageError: If the response appears to be a Google error page.
            ExactMatchNotFoundError: If the response cannot be classified as Exact
                Match HTML.
        """
        async with self.limiter.slot():
            await self.wait_before_upstream_request()
            response = await self.client.fetch_exact_match_html(image_url)

        if response.status_code >= 500:
            raise UpstreamRequestError("Google returned a server error")
        if response.status_code >= 400:
            raise UpstreamRequestError("Google returned a client error")

        classification = classify_google_html(response.html, response.final_url)
        if classification.verdict == HtmlVerdict.EXACT_MATCH:
            return ExactMatchHtml(html=response.html, source_url=response.final_url)
        if classification.verdict == HtmlVerdict.BOT_BLOCK:
            raise BotBlockError("Google returned CAPTCHA or bot-check HTML")
        if classification.verdict == HtmlVerdict.GOOGLE_ERROR:
            raise GoogleErrorPageError("Google returned an error page")

        raise ExactMatchNotFoundError("Google response was not Exact Match HTML")
