from __future__ import annotations

import unittest

from app.errors import MalformedImageUrlError
from app.models import ImageUrl


class ImageUrlParsingTests(unittest.TestCase):
    def test_parses_https_image_url(self) -> None:
        parsed = ImageUrl.parse("https://example.com/image.jpg")

        self.assertEqual(parsed.value, "https://example.com/image.jpg")
        self.assertEqual(parsed.parsed.netloc, "example.com")

    def test_trims_surrounding_space(self) -> None:
        parsed = ImageUrl.parse("  http://example.com/image.jpg  ")

        self.assertEqual(parsed.value, "http://example.com/image.jpg")

    def test_rejects_empty_url(self) -> None:
        with self.assertRaisesRegex(MalformedImageUrlError, "must not be empty"):
            ImageUrl.parse(" ")

    def test_rejects_unsupported_scheme(self) -> None:
        with self.assertRaisesRegex(MalformedImageUrlError, "http or https"):
            ImageUrl.parse("file:///tmp/image.jpg")

    def test_rejects_relative_url(self) -> None:
        with self.assertRaisesRegex(MalformedImageUrlError, "http or https"):
            ImageUrl.parse("/image.jpg")


if __name__ == "__main__":
    unittest.main()

