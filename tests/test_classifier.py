from __future__ import annotations

import unittest

from app.lens.classifier import HtmlVerdict, classify_google_html


class GoogleHtmlClassifierTests(unittest.TestCase):
    def test_detects_exact_match_html_markers(self) -> None:
        html = "<html><title>Google Lens</title><body>Exact matches</body></html>"

        classification = classify_google_html(html, "https://www.google.com/search?q=x")

        self.assertEqual(classification.verdict, HtmlVerdict.EXACT_MATCH)

    def test_detects_google_sorry_url_as_bot_block(self) -> None:
        classification = classify_google_html(
            "<html></html>",
            "https://www.google.com/sorry/index?continue=...",
        )

        self.assertEqual(classification.verdict, HtmlVerdict.BOT_BLOCK)

    def test_detects_recaptcha_marker_as_bot_block(self) -> None:
        classification = classify_google_html("<div class='g-recaptcha'></div>")

        self.assertEqual(classification.verdict, HtmlVerdict.BOT_BLOCK)

    def test_detects_google_error_marker(self) -> None:
        classification = classify_google_html("<html>Error 400 Bad Request</html>")

        self.assertEqual(classification.verdict, HtmlVerdict.GOOGLE_ERROR)

    def test_detects_google_forbidden_marker(self) -> None:
        classification = classify_google_html("<title>Error 403 (Forbidden)!!1</title>")

        self.assertEqual(classification.verdict, HtmlVerdict.GOOGLE_ERROR)

    def test_unknown_when_exact_match_markers_are_absent(self) -> None:
        classification = classify_google_html("<html><body>Search results</body></html>")

        self.assertEqual(classification.verdict, HtmlVerdict.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
