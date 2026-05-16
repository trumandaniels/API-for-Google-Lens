from __future__ import annotations

import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.errors import UpstreamTimeoutError
from app.lens.direct import DirectLensClient
from app.models import ImageUrl, ProviderApiToken


class TimeoutHttpClient:
    """Test double that raises a timeout for every request."""

    async def get(self, url: str, headers: dict[str, str]) -> object:
        """Raise an HTTPX timeout without performing network work."""
        import httpx

        raise httpx.TimeoutException("timed out")


class DirectLensClientTests(unittest.TestCase):
    def test_builds_google_lens_upload_by_url_request(self) -> None:
        client = DirectLensClient(
            google_base_url="https://lens.google.com/uploadbyurl",
            timeout_seconds=30,
            user_agent="test-agent",
            mrscraper_api_key="atk_example",
        )
        image_url = ImageUrl.parse("https://example.com/images/a b.jpg?size=large")

        request_url = client.build_exact_match_url(image_url)
        parsed = urlparse(request_url)
        query = parse_qs(parsed.query)

        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "lens.google.com")
        self.assertEqual(parsed.path, "/uploadbyurl")
        self.assertEqual(query["url"], ["https://example.com/images/a b.jpg?size=large"])
        self.assertNotIn("hl", query)
        self.assertNotIn("gl", query)
        self.assertNotIn("udm", query)

    def test_builds_exact_match_tab_url_from_lens_search_url(self) -> None:
        client = DirectLensClient(
            google_base_url="https://lens.google.com/uploadbyurl",
            timeout_seconds=30,
            user_agent="test-agent",
            mrscraper_api_key="atk_example",
        )

        request_url = client.build_exact_match_tab_url(
            "https://www.google.com/search?vsrid=abc&udm=26&hl=en"
        )
        parsed = urlparse(request_url)
        query = parse_qs(parsed.query)

        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "www.google.com")
        self.assertEqual(query["vsrid"], ["abc"])
        self.assertEqual(query["udm"], ["48"])
        self.assertEqual(query["hl"], ["en"])

    def test_builds_mrscraper_api_request_for_lens_url(self) -> None:
        client = DirectLensClient(
            google_base_url="https://lens.google.com/uploadbyurl",
            timeout_seconds=30,
            user_agent="test-agent",
            mrscraper_api_key="atk_example",
            mrscraper_api_url="https://api.mrscraper.com",
        )
        target_url = (
            "https://lens.google.com/uploadbyurl?"
            "url=https%3A%2F%2Fexample.com%2Fimage.jpg&hl=en&gl=US"
        )

        request_url = client.build_mrscraper_api_url(target_url)
        parsed = urlparse(request_url)
        query = parse_qs(parsed.query)

        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "api.mrscraper.com")
        self.assertEqual(query["html"], ["true"])
        self.assertEqual(query["super"], ["true"])
        self.assertNotIn("blockResources", query)
        self.assertEqual(query["url"], [target_url])
        self.assertEqual(query["token"], ["atk_example"])

    def test_can_override_mrscraper_token_per_request(self) -> None:
        client = DirectLensClient(
            google_base_url="https://lens.google.com/uploadbyurl",
            timeout_seconds=30,
            user_agent="test-agent",
            mrscraper_api_key="atk_configured",
            mrscraper_api_url="https://api.mrscraper.com",
        )
        override = ProviderApiToken.parse_optional(" atk_request ")
        assert override is not None

        headers = client.build_request_headers(override)
        request_url = client.build_mrscraper_api_url(
            "https://lens.google.com/uploadbyurl?url=x",
            override,
        )
        query = parse_qs(urlparse(request_url).query)

        self.assertEqual(headers["x-api-token"], "atk_request")
        self.assertEqual(query["token"], ["atk_request"])

    def test_can_enable_mrscraper_resource_blocking(self) -> None:
        client = DirectLensClient(
            google_base_url="https://lens.google.com/uploadbyurl",
            timeout_seconds=30,
            user_agent="test-agent",
            mrscraper_api_key="atk_example",
            block_resources=True,
        )

        request_url = client.build_mrscraper_api_url(
            "https://lens.google.com/uploadbyurl?url=https%3A%2F%2Fexample.com%2Fimage.jpg"
        )
        query = parse_qs(urlparse(request_url).query)

        self.assertEqual(query["blockResources"], ["true"])

    def test_finds_exact_match_tab_url_in_lens_search_fixture(self) -> None:
        client = DirectLensClient(
            google_base_url="https://lens.google.com/uploadbyurl",
            timeout_seconds=30,
            user_agent="test-agent",
            mrscraper_api_key="atk_example",
        )
        html = (
            Path(__file__).parent
            / "fixtures"
            / "google_lens"
            / "google-search-visual.html"
        ).read_text(encoding="utf-8", errors="replace")

        exact_url = client.find_exact_match_tab_url(html)

        self.assertIsNotNone(exact_url)
        assert exact_url is not None
        parsed = urlparse(exact_url)
        query = parse_qs(parsed.query)
        self.assertEqual(parsed.netloc, "www.google.com")
        self.assertEqual(query["udm"], ["48"])

    def test_mrscraper_api_key_is_required_for_api_url_builder(self) -> None:
        client = DirectLensClient(
            google_base_url="https://lens.google.com/uploadbyurl",
            timeout_seconds=30,
            user_agent="test-agent",
            mrscraper_api_key="",
        )

        with self.assertRaisesRegex(ValueError, "mrscraper_api_key is required"):
            client.build_mrscraper_api_url("https://lens.google.com/uploadbyurl?url=x")


class DirectLensClientAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_error_names_provider_hop(self) -> None:
        client = DirectLensClient(
            google_base_url="https://lens.google.com/uploadbyurl",
            timeout_seconds=30,
            user_agent="test-agent",
            mrscraper_api_key="atk_example",
            http_client=TimeoutHttpClient(),
        )

        with self.assertLogs("uvicorn.error", level="WARNING") as logs:
            with self.assertRaisesRegex(UpstreamTimeoutError, "lens_entry"):
                await client.fetch_exact_match_html(
                    ImageUrl.parse("https://example.com/image.jpg")
                )

        self.assertIn("lens_provider_hop_timeout hop=lens_entry", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()
