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


if __name__ == "__main__":
    unittest.main()

