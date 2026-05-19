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
from app.models import ImageUrl, ProviderApiToken
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
        self.last_token_override: ProviderApiToken | None = None
        self._lock = threading.Lock()

    async def fetch_exact_match_html(
        self,
        image_url: ImageUrl,
        token_override: ProviderApiToken | None = None,
    ) -> DirectLensResponse:
        """Return exact-match HTML after a short overlap window."""
        with self._lock:
            self.call_count += 1
            self.active_calls += 1
            self.max_active_calls = max(self.max_active_calls, self.active_calls)
            self.last_token_override = token_override

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

    def test_route_accepts_optional_mrscraper_token_override_header(self) -> None:
        settings = parse_settings(
            {
                "MRSCRAPER_API_KEY": "atk_configured",
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
            response = client.get(
                "/google-lens",
                params={"imageUrl": "https://example.com/image.jpg"},
                headers={"X-MrScraper-Api-Key": " atk_request "},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(counting_client.last_token_override)
        assert counting_client.last_token_override is not None
        self.assertEqual(counting_client.last_token_override.value, "atk_request")

    def test_route_logs_regular_request_without_raw_image_url(self) -> None:
        settings = parse_settings(
            {
                "MRSCRAPER_API_KEY": "atk_example",
                "REQUEST_DELAY_MIN_SECONDS": "0",
                "REQUEST_DELAY_MAX_SECONDS": "0",
            }
        )
        app = create_app(settings=settings)
        counting_client = CountingLensClient()
        image_url = "https://example.com/private/image.jpg?token=secret"

        with TestClient(app) as client:
            app.state.lens_service = GoogleLensService(
                client=counting_client,  # type: ignore[arg-type]
                limiter=AsyncConcurrencyLimiter(settings.max_concurrency),
                request_delay_min_seconds=0,
                request_delay_max_seconds=0,
            )
            with self.assertLogs("uvicorn.error", level="INFO") as logs:
                response = client.get("/google-lens", params={"imageUrl": image_url})

        joined_logs = "\n".join(logs.output)
        self.assertEqual(response.status_code, 200)
        self.assertIn("lens_api_request_started", joined_logs)
        self.assertIn("lens_api_request_completed", joined_logs)
        self.assertIn("image_url_hash=", joined_logs)
        self.assertIn("source_url_has_udm_48=True", joined_logs)
        self.assertNotIn(image_url, joined_logs)

    def test_route_logs_regular_request_failure(self) -> None:
        settings = parse_settings({"MRSCRAPER_API_KEY": "atk_example"})
        app = create_app(settings=settings)

        with TestClient(app) as client:
            with self.assertLogs("uvicorn.error", level="WARNING") as logs:
                response = client.get(
                    "/google-lens",
                    params={"imageUrl": "not-a-url"},
                )

        joined_logs = "\n".join(logs.output)
        self.assertEqual(response.status_code, 400)
        self.assertIn("lens_api_request_failed", joined_logs)
        self.assertIn("status=400", joined_logs)
        self.assertIn("error_type=MalformedImageUrlError", joined_logs)
        self.assertIn("image_url_hash=unparsed", joined_logs)


if __name__ == "__main__":
    unittest.main()
