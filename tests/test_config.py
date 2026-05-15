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
