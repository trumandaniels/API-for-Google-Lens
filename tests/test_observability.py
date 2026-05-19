from __future__ import annotations

from dataclasses import dataclass
import logging
import unittest
from unittest.mock import patch

from app.observability import (
    configure_logging,
    hash_url,
    log_lens_api_request_completed,
    log_measurement_result,
)


@dataclass(frozen=True)
class FakeMeasurementLogResult:
    """Minimal measurement result for logging helper tests."""

    index: int
    image_url_hash: str
    status_code: int | None
    latency_seconds: float
    verdict: str
    html_verdict: str
    error: str | None = None


class ObservabilityTests(unittest.TestCase):
    def test_hash_url_returns_stable_short_digest(self) -> None:
        raw_url = "https://example.com/private/image.jpg?token=secret"

        first = hash_url(raw_url)
        second = hash_url(raw_url)

        self.assertEqual(first, second)
        self.assertEqual(len(first), 16)
        self.assertNotIn("secret", first)

    def test_configure_logging_sets_requested_logger_level(self) -> None:
        logger = logging.getLogger("test_observability.configure")

        with patch("app.observability.logging.basicConfig") as basic_config:
            configure_logging(verbose=True, logger=logger)

        basic_config.assert_called_once()
        self.assertEqual(logger.level, logging.INFO)

        with patch("app.observability.logging.basicConfig"):
            configure_logging(verbose=False, logger=logger)

        self.assertEqual(logger.level, logging.WARNING)

    def test_measurement_log_helper_uses_hash_not_raw_url(self) -> None:
        raw_url = "https://example.com/private/image.jpg?token=secret"
        result = FakeMeasurementLogResult(
            index=7,
            image_url_hash=hash_url(raw_url),
            status_code=200,
            latency_seconds=1.5,
            verdict="valid_exact_match",
            html_verdict="exact_match",
        )

        with self.assertLogs("measure_lens_api", level="INFO") as captured:
            log_measurement_result(result)

        output = "\n".join(captured.output)
        self.assertIn("request_completed index=7", output)
        self.assertIn(result.image_url_hash, output)
        self.assertNotIn(raw_url, output)
        self.assertNotIn("secret", output)

    def test_api_log_helper_keeps_regular_request_fields_together(self) -> None:
        logger = logging.getLogger("test_observability.api")

        with self.assertLogs(logger, level="INFO") as captured:
            log_lens_api_request_completed(
                logger=logger,
                image_url_hash="abc123",
                elapsed_ms=12.5,
                response_bytes=100,
                source_url_has_udm_48=True,
                token_override_present=False,
            )

        output = "\n".join(captured.output)
        self.assertIn("lens_api_request_completed", output)
        self.assertIn("image_url_hash=abc123", output)
        self.assertIn("source_url_has_udm_48=True", output)


if __name__ == "__main__":
    unittest.main()
