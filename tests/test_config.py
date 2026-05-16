from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.config import parse_env_file, parse_settings


class SettingsParsingTests(unittest.TestCase):
    def test_parses_mrscraper_api_key(self) -> None:
        settings = parse_settings({"MRSCRAPER_API_KEY": "atk_example"})

        self.assertEqual(settings.mrscraper_api_key, "atk_example")
        self.assertEqual(settings.mrscraper_api_url, "https://api.mrscraper.com")
        self.assertGreater(settings.request_delay_max_seconds, 0)
        self.assertEqual(settings.response_cache_max_entries, 512)
        self.assertEqual(settings.response_cache_ttl_seconds, 7200.0)
        self.assertFalse(settings.mrscraper_block_resources)

    def test_parses_response_cache_settings(self) -> None:
        settings = parse_settings(
            {
                "MRSCRAPER_API_KEY": "atk_example",
                "RESPONSE_CACHE_MAX_ENTRIES": "32",
                "RESPONSE_CACHE_TTL_SECONDS": "120.5",
            }
        )

        self.assertEqual(settings.response_cache_max_entries, 32)
        self.assertEqual(settings.response_cache_ttl_seconds, 120.5)

    def test_requires_mrscraper_api_key(self) -> None:
        with self.assertRaisesRegex(ValueError, "MRSCRAPER_API_KEY"):
            parse_settings({})

    def test_rejects_non_https_mrscraper_api_url(self) -> None:
        with self.assertRaisesRegex(ValueError, "HTTPS URL"):
            parse_settings(
                {
                    "MRSCRAPER_API_KEY": "atk_example",
                    "MRSCRAPER_API_URL": "http://api.mrscraper.com",
                }
            )

    def test_rejects_invalid_delay_range(self) -> None:
        with self.assertRaisesRegex(ValueError, "REQUEST_DELAY_MAX_SECONDS"):
            parse_settings(
                {
                    "MRSCRAPER_API_KEY": "atk_example",
                    "REQUEST_DELAY_MIN_SECONDS": "2.0",
                    "REQUEST_DELAY_MAX_SECONDS": "1.0",
                }
            )

    def test_parses_local_env_file_subset(self) -> None:
        with TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "# local settings",
                        "export REQUEST_TIMEOUT_SECONDS = 45",
                        "USER_AGENT=Mozilla/5.0 (X11; Linux x86_64)",
                        "MRSCRAPER_API_KEY = 'atk_example'",
                    ]
                ),
                encoding="utf-8",
            )

            values = parse_env_file(env_path)

        self.assertEqual(values["REQUEST_TIMEOUT_SECONDS"], "45")
        self.assertEqual(values["USER_AGENT"], "Mozilla/5.0 (X11; Linux x86_64)")
        self.assertEqual(values["MRSCRAPER_API_KEY"], "atk_example")


if __name__ == "__main__":
    unittest.main()
