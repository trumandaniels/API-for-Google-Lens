from __future__ import annotations

import asyncio
import unittest

from app.errors import UpstreamRequestError
from app.lens.cache import ExactMatchResponseCache
from app.lens.direct import DirectLensResponse
from app.lens.service import GoogleLensService
from app.models import ExactMatchHtml, ImageUrl, ProviderApiToken
from app.throttling import AsyncConcurrencyLimiter


EXACT_MATCH_HTML = (
    '<html><body><div aria-current="page" selected="" class="mXwfNd">'
    '<span class="R1QWuf">Exact matches</span></div>'
    "<h1>Search Results</h1></body></html>"
)


class SequenceLensClient:
    """Test double that returns configured responses and counts upstream calls."""

    def __init__(self, responses: list[DirectLensResponse], delay_seconds: float = 0) -> None:
        self.responses = responses
        self.delay_seconds = delay_seconds
        self.call_count = 0

    async def fetch_exact_match_html(
        self,
        image_url: ImageUrl,
        token_override: ProviderApiToken | None = None,
    ) -> DirectLensResponse:
        """Return the next response in the configured sequence."""
        self.call_count += 1
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        index = min(self.call_count - 1, len(self.responses) - 1)
        return self.responses[index]


class MutableClock:
    """Small monotonic clock test double."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        """Return the current test timestamp."""
        return self.now


class ExactMatchResponseCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_service_caches_successful_exact_match_html_by_image_url(self) -> None:
        client = SequenceLensClient(
            [
                DirectLensResponse(
                    html=EXACT_MATCH_HTML,
                    final_url="https://www.google.com/search?udm=48",
                    status_code=200,
                )
            ]
        )
        service = GoogleLensService(
            client=client,  # type: ignore[arg-type]
            limiter=AsyncConcurrencyLimiter(1),
            cache=ExactMatchResponseCache(max_entries=10, ttl_seconds=3600),
        )
        image_url = ImageUrl.parse("https://example.com/image.jpg")

        first = await service.fetch_exact_match_html(image_url)
        second = await service.fetch_exact_match_html(image_url)

        self.assertEqual(first, second)
        self.assertEqual(client.call_count, 1)

    async def test_service_does_not_cache_upstream_failures(self) -> None:
        client = SequenceLensClient(
            [
                DirectLensResponse(
                    html="Forbidden",
                    final_url="https://api.mrscraper.com",
                    status_code=403,
                ),
                DirectLensResponse(
                    html=EXACT_MATCH_HTML,
                    final_url="https://www.google.com/search?udm=48",
                    status_code=200,
                ),
            ]
        )
        service = GoogleLensService(
            client=client,  # type: ignore[arg-type]
            limiter=AsyncConcurrencyLimiter(1),
            cache=ExactMatchResponseCache(max_entries=10, ttl_seconds=3600),
        )
        image_url = ImageUrl.parse("https://example.com/image.jpg")

        with self.assertRaisesRegex(UpstreamRequestError, "HTTP 403"):
            await service.fetch_exact_match_html(image_url)

        result = await service.fetch_exact_match_html(image_url)

        self.assertEqual(result.html, EXACT_MATCH_HTML)
        self.assertEqual(client.call_count, 2)

    async def test_service_coalesces_duplicate_in_flight_cache_misses(self) -> None:
        client = SequenceLensClient(
            [
                DirectLensResponse(
                    html=EXACT_MATCH_HTML,
                    final_url="https://www.google.com/search?udm=48",
                    status_code=200,
                )
            ],
            delay_seconds=0.05,
        )
        service = GoogleLensService(
            client=client,  # type: ignore[arg-type]
            limiter=AsyncConcurrencyLimiter(4),
            cache=ExactMatchResponseCache(max_entries=10, ttl_seconds=3600),
        )
        image_url = ImageUrl.parse("https://example.com/image.jpg")

        first, second = await asyncio.gather(
            service.fetch_exact_match_html(image_url),
            service.fetch_exact_match_html(image_url),
        )

        self.assertEqual(first, second)
        self.assertEqual(client.call_count, 1)

    async def test_cache_expires_entries_after_ttl(self) -> None:
        clock = MutableClock()
        cache = ExactMatchResponseCache(max_entries=10, ttl_seconds=5, clock=clock)
        calls = 0

        async def create_response() -> ExactMatchHtml:
            nonlocal calls
            calls += 1
            return ExactMatchHtml(
                html=f"<html>Exact matches {calls}</html>",
                source_url="https://www.google.com/search?udm=48",
            )

        first = await cache.get_or_create("https://example.com/image.jpg", create_response)
        clock.now = 6
        second = await cache.get_or_create("https://example.com/image.jpg", create_response)

        self.assertNotEqual(first.html, second.html)
        self.assertEqual(calls, 2)


if __name__ == "__main__":
    unittest.main()
