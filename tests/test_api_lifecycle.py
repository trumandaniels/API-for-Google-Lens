from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
import unittest

from fastapi.testclient import TestClient

from app.config import parse_settings
from app.lens.direct import DirectLensResponse
from app.lens.service import GoogleLensService
from app.main import build_lens_service, create_app
from app.models import ImageUrl
from app.throttling import AsyncConcurrencyLimiter


EXACT_MATCH_HTML = (
    '<html><body><div aria-current="page" selected="" class="mXwfNd">'
    '<span class="R1QWuf">Exact matches</span></div>'
    "<h1>Search Results</h1></body></html>"
)


class CountingLensClient:
    """Test double that records concurrent upstream entry count."""

    def __init__(self) -> None:
        self.active_calls = 0
        self.max_active_calls = 0
        self.call_count = 0
        self._lock = threading.Lock()

    async def fetch_exact_match_html(self, image_url: ImageUrl) -> DirectLensResponse:
        """Return exact-match HTML after a short overlap window."""
        with self._lock:
            self.call_count += 1
            self.active_calls += 1
            self.max_active_calls = max(self.max_active_calls, self.active_calls)

        await asyncio.sleep(0.05)

        with self._lock:
            self.active_calls -= 1

        return DirectLensResponse(
            html=EXACT_MATCH_HTML,
            final_url="https://www.google.com/search?udm=48",
            status_code=200,
        )


class ApiLifecycleTests(unittest.TestCase):
    def test_lens_service_is_initialized_once_in_app_state(self) -> None:
        settings = parse_settings({"MRSCRAPER_API_KEY": "atk_example"})
        app = create_app(settings=settings)

        with TestClient(app) as client:
            first_service = app.state.lens_service
            response = client.get("/healthz")
            second_service = app.state.lens_service

        self.assertEqual(response.status_code, 200)
        self.assertIs(first_service, second_service)
        self.assertTrue(first_service.client.http_client.is_closed)

    def test_lens_service_uses_process_scoped_http_client(self) -> None:
        settings = parse_settings({"MRSCRAPER_API_KEY": "atk_example"})
        service = build_lens_service(settings)

        try:
            self.assertIsNotNone(service.client.http_client)
            self.assertEqual(settings.max_concurrency, 16)
        finally:
            asyncio.run(service.aclose())

    def test_route_uses_shared_concurrency_limiter(self) -> None:
        settings = parse_settings(
            {
                "MRSCRAPER_API_KEY": "atk_example",
                "MAX_CONCURRENCY": "1",
                "REQUEST_DELAY_MIN_SECONDS": "0",
                "REQUEST_DELAY_MAX_SECONDS": "0",
            }
        )
        app = create_app(settings=settings)
        counting_client = CountingLensClient()

        with TestClient(app) as client:
            app.state.lens_service = GoogleLensService(
                client=counting_client,  # type: ignore[arg-type]
                limiter=AsyncConcurrencyLimiter(settings.max_concurrency),
                request_delay_min_seconds=0,
                request_delay_max_seconds=0,
            )

            def get_lens_html() -> int:
                response = client.get(
                    "/google-lens",
                    params={"imageUrl": "https://example.com/image.jpg"},
                )
                return response.status_code

            with ThreadPoolExecutor(max_workers=2) as executor:
                statuses = list(executor.map(lambda _: get_lens_html(), range(2)))

        self.assertEqual(statuses, [200, 200])
        self.assertEqual(counting_client.call_count, 2)
        self.assertEqual(counting_client.max_active_calls, 1)


if __name__ == "__main__":
    unittest.main()
