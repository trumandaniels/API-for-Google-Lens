from __future__ import annotations

import unittest

from app.config import build_mrscraper_proxy_url, parse_settings


class SettingsParsingTests(unittest.TestCase):
    def test_uses_explicit_proxy_url_when_configured(self) -> None:
        settings = parse_settings({"PROXY_URL": "http://proxy.example:8080"})

        self.assertEqual(settings.proxy_url, "http://proxy.example:8080")

    def test_parses_mrscraper_api_key(self) -> None:
        settings = parse_settings({"MRSCRAPER_API_KEY": "atk_example"})

        self.assertEqual(settings.mrscraper_api_key, "atk_example")
        self.assertEqual(settings.mrscraper_api_url, "https://api.mrscraper.com")

    def test_rejects_non_https_mrscraper_api_url(self) -> None:
        with self.assertRaisesRegex(ValueError, "HTTPS URL"):
            parse_settings({"MRSCRAPER_API_URL": "http://api.mrscraper.com"})

    def test_explicit_proxy_url_takes_precedence_over_mrscraper_credentials(self) -> None:
        settings = parse_settings(
            {
                "PROXY_URL": "http://proxy.example:8080",
                "MRSCRAPER_PROXY_USERNAME": "user123",
                "MRSCRAPER_PROXY_PASSWORD": "pass456",
                "MRSCRAPER_PROXY_COUNTRY": "us",
            }
        )

        self.assertEqual(settings.proxy_url, "http://proxy.example:8080")

    def test_builds_mrscraper_country_proxy_url(self) -> None:
        proxy_url = build_mrscraper_proxy_url(
            {
                "MRSCRAPER_PROXY_USERNAME": "user123",
                "MRSCRAPER_PROXY_PASSWORD": "pass456",
                "MRSCRAPER_PROXY_COUNTRY": "us",
            }
        )

        self.assertEqual(
            proxy_url,
            "http://user123-country-us:pass456@proxy.mrscraper.com:10000",
        )

    def test_builds_mrscraper_mobile_session_proxy_url(self) -> None:
        proxy_url = build_mrscraper_proxy_url(
            {
                "MRSCRAPER_PROXY_USERNAME": "user123",
                "MRSCRAPER_PROXY_PASSWORD": "pa:ss@456",
                "MRSCRAPER_PROXY_COUNTRY": "US",
                "MRSCRAPER_PROXY_MOBILE": "true",
                "MRSCRAPER_PROXY_SESSION_ID": "lens_1",
                "MRSCRAPER_PROXY_SESSION_MINUTES": "20",
            }
        )

        self.assertEqual(
            proxy_url,
            "http://user123-mobile-country-us-sessid-lens_1-sesstime-20:"
            "pa%3Ass%40456@proxy.mrscraper.com:10000",
        )

    def test_requires_both_mrscraper_credentials(self) -> None:
        with self.assertRaisesRegex(ValueError, "both MRSCRAPER_PROXY_USERNAME"):
            build_mrscraper_proxy_url({"MRSCRAPER_PROXY_USERNAME": "user123"})

    def test_rejects_malformed_mrscraper_country(self) -> None:
        with self.assertRaisesRegex(ValueError, "two-letter ISO"):
            build_mrscraper_proxy_url(
                {
                    "MRSCRAPER_PROXY_USERNAME": "user123",
                    "MRSCRAPER_PROXY_PASSWORD": "pass456",
                    "MRSCRAPER_PROXY_COUNTRY": "usa",
                }
            )

    def test_rejects_proxy_url_without_http_scheme(self) -> None:
        with self.assertRaisesRegex(ValueError, "http:// or https://"):
            parse_settings({"PROXY_URL": "socks5://proxy.example:1080"})


if __name__ == "__main__":
    unittest.main()
