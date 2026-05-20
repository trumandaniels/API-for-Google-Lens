from __future__ import annotations

from pathlib import Path
import unittest

from app.lens.classifier import HtmlVerdict, classify_google_html


class GoogleHtmlClassifierTests(unittest.TestCase):
    def test_detects_exact_match_html_markers(self) -> None:
        html = "<html><title>Search Results</title><body>Exact matches</body></html>"

        classification = classify_google_html(html, "https://www.google.com/search?udm=48")

        self.assertEqual(classification.verdict, HtmlVerdict.EXACT_MATCH)

    def test_detects_selected_exact_match_tab(self) -> None:
        html = (
            '<div aria-current="page" selected="" class="mXwfNd">'
            '<span class="R1QWuf">Exact matches</span></div>'
        )

        classification = classify_google_html(html)

        self.assertEqual(classification.verdict, HtmlVerdict.EXACT_MATCH)

    def test_detects_localized_selected_exact_match_tab(self) -> None:
        html = (
            '<div aria-current="page" selected="" class="mXwfNd">'
            '<span class="R1QWuf">Kecocokan persis</span></div>'
        )

        classification = classify_google_html(html)

        self.assertEqual(classification.verdict, HtmlVerdict.EXACT_MATCH)

    def test_fixture_all_tab_pages_are_not_exact_match_success(self) -> None:
        fixture_dir = Path(__file__).parent / "fixtures" / "google_lens"
        for fixture_path in fixture_dir.glob("google-search-*.html"):
            with self.subTest(fixture=fixture_path.name):
                classification = classify_google_html(
                    fixture_path.read_text(encoding="utf-8", errors="replace"),
                    "https://www.google.com/search?udm=26",
                )

                self.assertEqual(classification.verdict, HtmlVerdict.UNKNOWN)

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

    def test_detects_exact_match_no_results_empty_state(self) -> None:
        html = (
            '<div aria-current="page" selected="" class="mXwfNd">'
            '<span class="R1QWuf">Exact matches</span></div>'
            "<h2>No matches for your search</h2>"
            "<p>To get better results, try changing the search area "
            "or submitting another image.</p>"
        )

        classification = classify_google_html(html)

        self.assertEqual(classification.verdict, HtmlVerdict.NO_MATCH)

    def test_detects_localized_exact_match_no_results_empty_state(self) -> None:
        html = (
            '<div aria-current="page" selected="" class="mXwfNd">'
            '<span class="R1QWuf">Kecocokan persis</span></div>'
            "<h2>Tidak ada kecocokan untuk penelusuran Anda</h2>"
            "<p>Untuk mendapatkan hasil yang lebih baik, coba ubah area "
            "penelusuran atau kirim gambar lain</p>"
        )

        classification = classify_google_html(html)

        self.assertEqual(classification.verdict, HtmlVerdict.NO_MATCH)

    def test_unknown_when_exact_match_markers_are_absent(self) -> None:
        classification = classify_google_html("<html><body>Search results</body></html>")

        self.assertEqual(classification.verdict, HtmlVerdict.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
