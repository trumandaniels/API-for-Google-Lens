from __future__ import annotations

import importlib.util
from argparse import Namespace
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "scripts" / "measure_lens_api.py"
MODULE_SPEC = importlib.util.spec_from_file_location("measure_lens_api", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"Unable to load module from {MODULE_PATH}")
measure_lens_api = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = measure_lens_api
MODULE_SPEC.loader.exec_module(measure_lens_api)


class MeasureLensApiTests(unittest.TestCase):
    def test_classifies_exact_match_response_as_valid(self) -> None:
        verdict, html_verdict = measure_lens_api.classify_response(
            200,
            (
                '<div aria-current="page" selected="" class="mXwfNd">'
                '<span class="R1QWuf">Exact matches</span></div>'
            ),
            "http://127.0.0.1:8000/google-lens",
        )

        self.assertEqual(verdict, "valid_exact_match")
        self.assertEqual(html_verdict, "exact_match")

    def test_classifies_non_exact_success_as_invalid_2xx(self) -> None:
        verdict, html_verdict = measure_lens_api.classify_response(
            200,
            "<html><body>Search Results</body></html>",
            "http://127.0.0.1:8000/google-lens",
        )

        self.assertEqual(verdict, "invalid_2xx")
        self.assertEqual(html_verdict, "unknown")

    def test_summarizes_json_error_detail_without_full_body(self) -> None:
        detail = measure_lens_api.summarize_error_detail(
            502,
            '{"detail":"Provider or Google returned HTTP 503"}',
            "http_error",
        )

        self.assertEqual(detail, "Provider or Google returned HTTP 503")

    def test_summarizes_invalid_2xx_detail(self) -> None:
        detail = measure_lens_api.summarize_error_detail(
            200,
            "<html>Search Results</html>",
            "invalid_2xx",
        )

        self.assertEqual(detail, "2xx response did not classify as Exact Match HTML")

    def test_builds_deterministic_image_url_schedule_by_cycling(self) -> None:
        schedule = measure_lens_api.build_image_url_schedule(
            ["https://example.com/a.jpg", "https://example.com/b.jpg"],
            request_count=5,
            randomize=False,
        )

        self.assertEqual(
            schedule,
            [
                "https://example.com/a.jpg",
                "https://example.com/b.jpg",
                "https://example.com/a.jpg",
                "https://example.com/b.jpg",
                "https://example.com/a.jpg",
            ],
        )

    def test_builds_seeded_random_image_url_schedule_without_replacement_per_cycle(self) -> None:
        image_urls = [
            "https://example.com/a.jpg",
            "https://example.com/b.jpg",
            "https://example.com/c.jpg",
        ]

        first = measure_lens_api.build_image_url_schedule(
            image_urls,
            request_count=5,
            randomize=True,
            seed=7,
        )
        second = measure_lens_api.build_image_url_schedule(
            image_urls,
            request_count=5,
            randomize=True,
            seed=7,
        )

        self.assertEqual(first, second)
        self.assertEqual(set(first[:3]), set(image_urls))

    def test_summarizes_metrics_and_threshold_checks(self) -> None:
        results = [
            measure_lens_api.MeasurementResult(
                index=0,
                image_url_hash="a",
                status_code=200,
                latency_seconds=1.0,
                verdict="valid_exact_match",
                html_verdict="exact_match",
            ),
            measure_lens_api.MeasurementResult(
                index=1,
                image_url_hash="b",
                status_code=502,
                latency_seconds=3.0,
                verdict="http_error",
                html_verdict="unknown",
            ),
            measure_lens_api.MeasurementResult(
                index=2,
                image_url_hash="c",
                status_code=200,
                latency_seconds=2.0,
                verdict="invalid_2xx",
                html_verdict="unknown",
            ),
        ]
        thresholds = measure_lens_api.Thresholds(
            min_valid_exact=1,
            max_average_latency_seconds=2.1,
            max_error_rate=0.67,
        )

        summary = measure_lens_api.summarize_results(results, thresholds)

        self.assertTrue(summary["passed"])
        self.assertEqual(summary["metrics"]["totalRequests"], 3)
        self.assertEqual(summary["metrics"]["validExactMatchCount"], 1)
        self.assertEqual(summary["metrics"]["invalid2xxCount"], 1)
        self.assertAlmostEqual(summary["metrics"]["averageLatencySeconds"], 2.0)
        self.assertEqual(summary["metrics"]["errorCount"], 2)
        self.assertAlmostEqual(summary["metrics"]["errorRate"], 2 / 3)
        self.assertIsNone(summary["projectedHourEstimate"])

    def test_summarizes_projected_hour_estimate(self) -> None:
        results = [
            measure_lens_api.MeasurementResult(
                index=index,
                image_url_hash=str(index),
                status_code=200,
                latency_seconds=1.0,
                verdict="valid_exact_match",
                html_verdict="exact_match",
            )
            for index in range(2)
        ]

        summary = measure_lens_api.summarize_results(
            results,
            thresholds=None,
            projection_multiplier=12.0,
        )

        self.assertEqual(summary["projectedHourEstimate"]["totalRequests"], 24)
        self.assertEqual(summary["projectedHourEstimate"]["validExactMatchCount"], 24)
        self.assertEqual(summary["projectedHourEstimate"]["errorRate"], 0.0)

    def test_summarizes_observed_hour_estimate_from_elapsed_time(self) -> None:
        results = [
            measure_lens_api.MeasurementResult(
                index=index,
                image_url_hash=str(index),
                status_code=200,
                latency_seconds=2.0,
                verdict="valid_exact_match",
                html_verdict="exact_match",
            )
            for index in range(10)
        ]

        summary = measure_lens_api.summarize_results(
            results,
            thresholds=None,
            elapsed_seconds=120.0,
        )

        self.assertEqual(summary["observedHourEstimate"]["totalRequests"], 300)
        self.assertEqual(
            summary["observedHourEstimate"]["validExactMatchCount"],
            300,
        )
        self.assertEqual(summary["observedHourEstimate"]["requestsPerMinute"], 5.0)
        self.assertTrue(summary["observedHourChallengePassed"])

    def test_five_minute_estimate_uses_scaled_challenge_threshold(self) -> None:
        args = Namespace(
            target="five-minute-estimate",
            projection_multiplier=None,
            min_valid_exact=None,
            max_average_latency_seconds=None,
            max_error_rate=None,
        )

        projection_multiplier = measure_lens_api.resolve_projection_multiplier(args)
        thresholds = measure_lens_api.build_thresholds(args, projection_multiplier)

        self.assertEqual(projection_multiplier, 12.0)
        self.assertEqual(thresholds.min_valid_exact, 25)
        self.assertEqual(thresholds.max_average_latency_seconds, 60.0)
        self.assertEqual(thresholds.max_error_rate, 0.10)

    def test_resolves_mrscraper_override_header_from_env_name(self) -> None:
        headers = measure_lens_api.resolve_request_headers(
            "MRSCRAPER_API_KEY",
            {"MRSCRAPER_API_KEY": " atk_example "},
        )

        self.assertEqual(headers, {"X-MrScraper-Api-Key": "atk_example"})

    def test_rejects_empty_mrscraper_override_header_env_value(self) -> None:
        with self.assertRaisesRegex(ValueError, "MRSCRAPER_API_KEY"):
            measure_lens_api.resolve_request_headers(
                "MRSCRAPER_API_KEY",
                {"MRSCRAPER_API_KEY": " "},
            )

    def test_threshold_failure_is_reported(self) -> None:
        results = [
            measure_lens_api.MeasurementResult(
                index=0,
                image_url_hash="a",
                status_code=502,
                latency_seconds=61.0,
                verdict="http_error",
                html_verdict="unknown",
            )
        ]
        thresholds = measure_lens_api.Thresholds(
            min_valid_exact=1,
            max_average_latency_seconds=60.0,
            max_error_rate=0.10,
        )

        summary = measure_lens_api.summarize_results(results, thresholds)

        self.assertFalse(summary["passed"])
        self.assertFalse(summary["checks"]["validExactMatchCount"])
        self.assertFalse(summary["checks"]["averageLatencySeconds"])
        self.assertFalse(summary["checks"]["errorRate"])


if __name__ == "__main__":
    unittest.main()
