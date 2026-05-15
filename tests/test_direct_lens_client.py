from __future__ import annotations

import unittest
from urllib.parse import parse_qs, urlparse

from app.lens.direct import DirectLensClient
from app.models import ImageUrl


class DirectLensClientTests(unittest.TestCase):
    def test_builds_google_lens_upload_by_url_request(self) -> None:
        client = DirectLensClient(
            google_base_url="https://lens.google.com/uploadbyurl",
            timeout_seconds=30,
            user_agent="test-agent",
        )
        image_url = ImageUrl.parse("https://example.com/images/a b.jpg?size=large")

        request_url = client.build_exact_match_url(image_url)
        parsed = urlparse(request_url)
        query = parse_qs(parsed.query)

        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "lens.google.com")
        self.assertEqual(parsed.path, "/uploadbyurl")
        self.assertEqual(query["url"], ["https://example.com/images/a b.jpg?size=large"])
        self.assertEqual(query["hl"], ["en"])
        self.assertEqual(query["gl"], ["US"])
        self.assertEqual(query["udm"], ["26"])

    def test_builds_exact_match_tab_url_from_lens_search_url(self) -> None:
        client = DirectLensClient(
            google_base_url="https://lens.google.com/uploadbyurl",
            timeout_seconds=30,
            user_agent="test-agent",
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
        self.assertEqual(query["timeout"], ["30"])
        self.assertEqual(query["geoCode"], ["US"])
        self.assertEqual(query["blockResources"], ["false"])
        self.assertEqual(query["url"], [target_url])
        self.assertEqual(query["token"], ["atk_example"])

    def test_direct_proxy_takes_precedence_over_mrscraper_api_token(self) -> None:
        client = DirectLensClient(
            google_base_url="https://lens.google.com/uploadbyurl",
            timeout_seconds=30,
            user_agent="test-agent",
            mrscraper_api_key="atk_example",
            proxy_url="http://proxy.example:8080",
        )

        self.assertFalse(client.uses_mrscraper_api)


if __name__ == "__main__":
    unittest.main()
