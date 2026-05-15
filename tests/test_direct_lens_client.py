from __future__ import annotations

import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.lens.direct import DirectLensClient
from app.models import ImageUrl


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
        self.assertEqual(query["url"], [target_url])
        self.assertEqual(query["token"], ["atk_example"])

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


if __name__ == "__main__":
    unittest.main()
