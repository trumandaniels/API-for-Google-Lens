#!/usr/bin/env python3

"""Measure Google Lens API latency, validity, and error rates.

This script sends requests to a running `/google-lens` API, classifies returned
HTML, and writes reproducible artifacts under `.runtime/runs/`.

Example:
    python3 scripts/measure_lens_api.py \\
        --base-url http://127.0.0.1:8000 \\
        --image-url https://example.com/image.jpg \\
        --requests 5 \\
        --concurrency 2

Challenge-style run:
    python3 scripts/measure_lens_api.py \\
        --base-url https://your-host.example \\
        --image-url-file .runtime/live-image-urls.txt \\
        --requests 1000 \\
        --concurrency 4 \\
        --rate-per-minute 16.7 \\
        --target challenge

Credit-conscious five-minute estimate:
    python3 scripts/measure_lens_api.py \\
        --base-url https://your-host.example \\
        --image-url-file .runtime/live-image-urls.txt \\
        --requests 84 \\
        --concurrency 4 \\
        --rate-per-minute 16.7 \\
        --target five-minute-estimate
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import random
import statistics
import time
from typing import Any
from urllib.parse import urljoin

from app.config import parse_env_file
from app.lens.classifier import HtmlVerdict, classify_google_html

CHALLENGE_MIN_VALID_EXACT = 300
CHALLENGE_MAX_AVERAGE_LATENCY_SECONDS = 60.0
CHALLENGE_MAX_ERROR_RATE = 0.10
FIVE_MINUTE_PROJECTION_MULTIPLIER = 12.0


@dataclass(frozen=True)
class MeasurementResult:
    """Single API request measurement.

    Attributes:
        index: Zero-based request index.
        image_url_hash: SHA-256 prefix for the image URL, avoiding raw URL logs.
        status_code: HTTP status code returned by the API, or `None` on network
            failure.
        latency_seconds: End-to-end API latency.
        verdict: Response verdict used for aggregate metrics.
        html_verdict: HTML classifier verdict when a response body exists.
        error: Short failure description, if any.
    """

    index: int
    image_url_hash: str
    status_code: int | None
    latency_seconds: float
    verdict: str
    html_verdict: str
    error: str | None = None


@dataclass(frozen=True)
class Thresholds:
    """Pass/fail thresholds for a measurement run.

    Attributes:
        min_valid_exact: Minimum valid Exact Match responses required.
        max_average_latency_seconds: Maximum allowed average request latency.
        max_error_rate: Maximum allowed HTTP/network error rate.
    """

    min_valid_exact: int
    max_average_latency_seconds: float
    max_error_rate: float


def utc_timestamp() -> str:
    """Return the current UTC time as an ISO-8601 string."""

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_timestamp() -> str:
    """Return a timestamp safe for directory names."""

    return utc_timestamp().replace(":", "-").replace(".", "-")


def hash_url(url: str) -> str:
    """Return a short stable hash for a URL.

    Args:
        url: Image URL that should not be stored verbatim in artifacts.

    Returns:
        First 16 hex characters of the URL SHA-256 digest.
    """

    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def load_image_urls(image_urls: list[str], image_url_file: Path | None) -> list[str]:
    """Load and parse image URLs from CLI values and an optional file.

    Args:
        image_urls: URLs provided with repeated `--image-url` flags.
        image_url_file: Optional newline-delimited URL file.

    Returns:
        Non-empty list of stripped image URLs.

    Raises:
        ValueError: If no URLs are provided.
    """

    loaded_urls = [url.strip() for url in image_urls if url.strip()]
    if image_url_file is not None:
        for line in image_url_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                loaded_urls.append(stripped)
    if not loaded_urls:
        raise ValueError("at least one --image-url or --image-url-file entry is required")
    return loaded_urls


def build_image_url_schedule(
    image_urls: list[str],
    request_count: int,
    randomize: bool,
    seed: int | None = None,
) -> list[str]:
    """Build the per-request image URL schedule.

    Args:
        image_urls: Candidate image URLs.
        request_count: Number of API requests to schedule.
        randomize: Whether to randomize URL order.
        seed: Optional random seed for reproducible measurements.

    Returns:
        Image URL list with exactly `request_count` entries. Randomized
        schedules sample without replacement until the input set is exhausted,
        then reshuffle for the next cycle.

    Raises:
        ValueError: If `request_count` is less than one.
    """

    if request_count < 1:
        raise ValueError("--requests must be at least 1")

    if not randomize:
        return [image_urls[index % len(image_urls)] for index in range(request_count)]

    rng = random.Random(seed)
    schedule: list[str] = []
    while len(schedule) < request_count:
        batch = list(image_urls)
        rng.shuffle(batch)
        schedule.extend(batch)
    return schedule[:request_count]


def percentile(values: list[float], percentile_value: float) -> float:
    """Return a nearest-rank percentile from numeric values.

    Args:
        values: Values to summarize.
        percentile_value: Percentile between 0 and 100.

    Returns:
        Percentile value, or `0.0` when the input is empty.
    """

    if not values:
        return 0.0
    sorted_values = sorted(values)
    rank = max(1, round((percentile_value / 100) * len(sorted_values)))
    return sorted_values[min(rank, len(sorted_values)) - 1]


def classify_response(status_code: int, body: str, final_url: str) -> tuple[str, str]:
    """Classify an API response for measurement aggregation.

    Args:
        status_code: API HTTP status code.
        body: Response text.
        final_url: Final response URL.

    Returns:
        Pair of aggregate verdict and HTML classifier verdict.
    """

    html_classification = classify_google_html(body, final_url)
    html_verdict = str(html_classification.verdict)
    if status_code == 200 and html_classification.verdict == HtmlVerdict.EXACT_MATCH:
        return "valid_exact_match", html_verdict
    if status_code == 200:
        return "invalid_2xx", html_verdict
    if status_code == 429 or html_classification.verdict == HtmlVerdict.BOT_BLOCK:
        return "bot_block", html_verdict
    return "http_error", html_verdict


def summarize_error_detail(status_code: int, body: str, verdict: str) -> str | None:
    """Return a short API-safe error detail for failed measurements.

    Args:
        status_code: HTTP status code returned by the measured API.
        body: Response body returned by the measured API.
        verdict: Aggregate response verdict.

    Returns:
        Short diagnostic detail for non-successful measurements, or `None` for
        valid Exact Match responses.
    """

    if verdict == "valid_exact_match":
        return None
    if status_code == 200:
        return "2xx response did not classify as Exact Match HTML"

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, dict) and isinstance(parsed.get("detail"), str):
        detail = parsed["detail"]
    else:
        detail = body

    compact = " ".join(detail.split())
    if len(compact) > 240:
        return compact[:237] + "..."
    return compact or None


def summarize_results(
    results: list[MeasurementResult],
    thresholds: Thresholds | None,
    projection_multiplier: float | None = None,
    elapsed_seconds: float | None = None,
) -> dict[str, Any]:
    """Summarize request measurements and compute threshold verdicts.

    Invalid 2xx responses count toward `errorRate` because challenge scoring
    cares whether the API returned valid Exact Match HTML, not just whether the
    HTTP transport completed successfully.

    Args:
        results: Per-request measurements.
        thresholds: Optional pass/fail thresholds.
        projection_multiplier: Optional count multiplier for planned-duration
            projections, such as 5-minute-to-1-hour estimates.
        elapsed_seconds: Optional measured wall-clock duration. When provided,
            the summary includes an observed-throughput 1-hour estimate.

    Returns:
        JSON-serializable summary object.
    """

    total = len(results)
    latencies = [result.latency_seconds for result in results]
    valid_exact = sum(result.verdict == "valid_exact_match" for result in results)
    invalid_2xx = sum(result.verdict == "invalid_2xx" for result in results)
    bot_blocks = sum(result.verdict == "bot_block" for result in results)
    http_errors = sum(result.verdict == "http_error" for result in results)
    network_errors = sum(result.verdict == "network_error" for result in results)
    error_count = http_errors + network_errors + bot_blocks + invalid_2xx

    metrics: dict[str, Any] = {
        "totalRequests": total,
        "validExactMatchCount": valid_exact,
        "invalid2xxCount": invalid_2xx,
        "botBlockCount": bot_blocks,
        "httpErrorCount": http_errors,
        "networkErrorCount": network_errors,
        "errorCount": error_count,
        "validExactMatchRate": valid_exact / total if total else 0.0,
        "errorRate": error_count / total if total else 0.0,
        "averageLatencySeconds": statistics.fmean(latencies) if latencies else 0.0,
        "p50LatencySeconds": percentile(latencies, 50),
        "p95LatencySeconds": percentile(latencies, 95),
        "maxLatencySeconds": max(latencies) if latencies else 0.0,
    }
    projected_hour_estimate = None
    if projection_multiplier is not None:
        projected_hour_estimate = {
            "projectionMultiplier": projection_multiplier,
            "totalRequests": round(total * projection_multiplier),
            "validExactMatchCount": round(valid_exact * projection_multiplier),
            "invalid2xxCount": round(invalid_2xx * projection_multiplier),
            "botBlockCount": round(bot_blocks * projection_multiplier),
            "httpErrorCount": round(http_errors * projection_multiplier),
            "networkErrorCount": round(network_errors * projection_multiplier),
            "errorCount": round(error_count * projection_multiplier),
            "validExactMatchRate": metrics["validExactMatchRate"],
            "errorRate": metrics["errorRate"],
            "averageLatencySeconds": metrics["averageLatencySeconds"],
            "p50LatencySeconds": metrics["p50LatencySeconds"],
            "p95LatencySeconds": metrics["p95LatencySeconds"],
            "maxLatencySeconds": metrics["maxLatencySeconds"],
        }
    observed_hour_estimate = None
    observed_hour_checks: dict[str, bool] | None = None
    observed_hour_passed: bool | None = None
    if elapsed_seconds is not None and elapsed_seconds > 0:
        observed_multiplier = 3600.0 / elapsed_seconds
        observed_hour_estimate = {
            "elapsedSeconds": elapsed_seconds,
            "projectionMultiplier": observed_multiplier,
            "requestsPerMinute": total / (elapsed_seconds / 60.0),
            "totalRequests": round(total * observed_multiplier),
            "validExactMatchCount": round(valid_exact * observed_multiplier),
            "invalid2xxCount": round(invalid_2xx * observed_multiplier),
            "botBlockCount": round(bot_blocks * observed_multiplier),
            "httpErrorCount": round(http_errors * observed_multiplier),
            "networkErrorCount": round(network_errors * observed_multiplier),
            "errorCount": round(error_count * observed_multiplier),
            "validExactMatchRate": metrics["validExactMatchRate"],
            "errorRate": metrics["errorRate"],
            "averageLatencySeconds": metrics["averageLatencySeconds"],
            "p50LatencySeconds": metrics["p50LatencySeconds"],
            "p95LatencySeconds": metrics["p95LatencySeconds"],
            "maxLatencySeconds": metrics["maxLatencySeconds"],
        }
        observed_hour_checks = {
            "validExactMatchCount": (
                observed_hour_estimate["validExactMatchCount"]
                >= CHALLENGE_MIN_VALID_EXACT
            ),
            "averageLatencySeconds": (
                metrics["averageLatencySeconds"]
                <= CHALLENGE_MAX_AVERAGE_LATENCY_SECONDS
            ),
            "errorRate": metrics["errorRate"] <= CHALLENGE_MAX_ERROR_RATE,
        }
        observed_hour_passed = all(observed_hour_checks.values())

    checks: dict[str, bool] = {}
    if thresholds is not None:
        checks = {
            "validExactMatchCount": valid_exact >= thresholds.min_valid_exact,
            "averageLatencySeconds": (
                metrics["averageLatencySeconds"] <= thresholds.max_average_latency_seconds
            ),
            "errorRate": metrics["errorRate"] <= thresholds.max_error_rate,
        }

    return {
        "checks": checks,
        "metrics": metrics,
        "observedHourChallengeChecks": observed_hour_checks,
        "observedHourChallengePassed": observed_hour_passed,
        "observedHourEstimate": observed_hour_estimate,
        "passed": all(checks.values()) if checks else None,
        "projectedHourEstimate": projected_hour_estimate,
        "thresholds": asdict(thresholds) if thresholds is not None else None,
    }


async def measure_one(
    client: Any,
    endpoint_url: str,
    image_url: str,
    index: int,
    request_headers: dict[str, str] | None = None,
) -> MeasurementResult:
    """Measure one `/google-lens` request.

    Args:
        client: Async HTTP client with a `get` method.
        endpoint_url: Full `/google-lens` URL.
        image_url: Image URL to submit.
        index: Request index.
        request_headers: Optional HTTP headers to send with the API request.

    Returns:
        Per-request measurement.
    """

    started = time.perf_counter()
    try:
        response = await client.get(
            endpoint_url,
            params={"imageUrl": image_url},
            headers=request_headers,
        )
        latency = time.perf_counter() - started
        verdict, html_verdict = classify_response(
            response.status_code,
            response.text,
            str(response.url),
        )
        error_detail = summarize_error_detail(
            response.status_code,
            response.text,
            verdict,
        )
        return MeasurementResult(
            index=index,
            image_url_hash=hash_url(image_url),
            status_code=response.status_code,
            latency_seconds=latency,
            verdict=verdict,
            html_verdict=html_verdict,
            error=error_detail,
        )
    except Exception as error:
        latency = time.perf_counter() - started
        return MeasurementResult(
            index=index,
            image_url_hash=hash_url(image_url),
            status_code=None,
            latency_seconds=latency,
            verdict="network_error",
            html_verdict="unknown",
            error=type(error).__name__,
        )


async def run_measurement(
    base_url: str,
    image_url_schedule: list[str],
    request_count: int,
    concurrency: int,
    rate_per_minute: float | None,
    timeout_seconds: float,
    request_headers: dict[str, str] | None = None,
) -> list[MeasurementResult]:
    """Run a latency and validity measurement set.

    Args:
        base_url: Base API URL.
        image_url_schedule: Per-request image URL schedule.
        request_count: Number of API requests to send.
        concurrency: Maximum concurrent API requests.
        rate_per_minute: Optional launch rate. `None` starts work as quickly as
            concurrency allows.
        timeout_seconds: Per-request client timeout.
        request_headers: Optional HTTP headers to send with every API request.

    Returns:
        Per-request measurements.
    """

    if request_count < 1:
        raise ValueError("--requests must be at least 1")
    if len(image_url_schedule) != request_count:
        raise ValueError("image URL schedule length must match --requests")
    if concurrency < 1:
        raise ValueError("--concurrency must be at least 1")
    if rate_per_minute is not None and rate_per_minute <= 0:
        raise ValueError("--rate-per-minute must be positive when provided")

    import httpx

    endpoint_url = urljoin(base_url.rstrip("/") + "/", "google-lens")
    semaphore = asyncio.Semaphore(concurrency)
    launch_interval = 60.0 / rate_per_minute if rate_per_minute else 0.0
    results: list[MeasurementResult] = []

    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds)) as client:

        async def run_index(index: int) -> None:
            async with semaphore:
                image_url = image_url_schedule[index]
                result = await measure_one(
                    client,
                    endpoint_url,
                    image_url,
                    index,
                    request_headers,
                )
                results.append(result)

        tasks: list[asyncio.Task[None]] = []
        for index in range(request_count):
            tasks.append(asyncio.create_task(run_index(index)))
            if launch_interval:
                await asyncio.sleep(launch_interval)

        await asyncio.gather(*tasks)

    return sorted(results, key=lambda result: result.index)


def write_json(path: Path, value: object) -> None:
    """Write JSON with a trailing newline."""

    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, results: list[MeasurementResult]) -> None:
    """Write request measurements as JSON Lines."""

    lines = [json.dumps(asdict(result), sort_keys=True) for result in results]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_markdown_report(summary: dict[str, Any], run_config: dict[str, Any]) -> str:
    """Render a compact human-readable measurement report."""

    metrics = summary["metrics"]
    observed_hour_estimate = summary["observedHourEstimate"]
    projected_hour_estimate = summary["projectedHourEstimate"]
    thresholds = summary["thresholds"]
    lines = [
        "# Google Lens API Measurement",
        "",
        f"- Started at: `{run_config['startedAt']}`",
        f"- Base URL: `{run_config['baseUrl']}`",
        f"- Requests: `{metrics['totalRequests']}`",
        f"- Concurrency: `{run_config['concurrency']}`",
        f"- Rate per minute: `{run_config['ratePerMinute']}`",
        "",
        "## Metrics",
        "",
        f"- Valid Exact Match responses: `{metrics['validExactMatchCount']}`",
        f"- Valid Exact Match rate: `{metrics['validExactMatchRate']:.3f}`",
        f"- Error rate: `{metrics['errorRate']:.3f}`",
        f"- Average latency seconds: `{metrics['averageLatencySeconds']:.3f}`",
        f"- p50 latency seconds: `{metrics['p50LatencySeconds']:.3f}`",
        f"- p95 latency seconds: `{metrics['p95LatencySeconds']:.3f}`",
        f"- Max latency seconds: `{metrics['maxLatencySeconds']:.3f}`",
        f"- Bot blocks: `{metrics['botBlockCount']}`",
        f"- HTTP errors: `{metrics['httpErrorCount']}`",
        f"- Invalid 2xx responses: `{metrics['invalid2xxCount']}`",
    ]
    if projected_hour_estimate is not None:
        lines.extend(
            [
                "",
                "## Projected Hour Estimate",
                "",
                (
                    "- Projection multiplier: "
                    f"`{projected_hour_estimate['projectionMultiplier']}`"
                ),
                (
                    "- Projected total requests: "
                    f"`{projected_hour_estimate['totalRequests']}`"
                ),
                (
                    "- Projected valid Exact Match responses: "
                    f"`{projected_hour_estimate['validExactMatchCount']}`"
                ),
                f"- Projected error rate: `{projected_hour_estimate['errorRate']:.3f}`",
                (
                    "- Projected average latency seconds: "
                    f"`{projected_hour_estimate['averageLatencySeconds']:.3f}`"
                ),
            ]
        )
    if observed_hour_estimate is not None:
        lines.extend(
            [
                "",
                "## Observed-Throughput Hour Estimate",
                "",
                f"- Elapsed seconds: `{observed_hour_estimate['elapsedSeconds']:.3f}`",
                (
                    "- Observed requests per minute: "
                    f"`{observed_hour_estimate['requestsPerMinute']:.3f}`"
                ),
                (
                    "- Observed-throughput projected total requests: "
                    f"`{observed_hour_estimate['totalRequests']}`"
                ),
                (
                    "- Observed-throughput projected valid Exact Match responses: "
                    f"`{observed_hour_estimate['validExactMatchCount']}`"
                ),
                (
                    "- Observed-throughput challenge passed: "
                    f"`{summary['observedHourChallengePassed']}`"
                ),
            ]
        )
    if thresholds is not None:
        lines.extend(
            [
                "",
                "## Threshold Verdict",
                "",
                f"- Passed: `{summary['passed']}`",
                f"- Minimum valid Exact Match responses: `{thresholds['min_valid_exact']}`",
                (
                    "- Maximum average latency seconds: "
                    f"`{thresholds['max_average_latency_seconds']}`"
                ),
                f"- Maximum error rate: `{thresholds['max_error_rate']}`",
            ]
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--image-url", action="append", default=[])
    parser.add_argument("--image-url-file", type=Path)
    parser.add_argument("--requests", type=int, default=1)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--rate-per-minute", type=float)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--randomize-image-urls",
        action="store_true",
        help=(
            "Shuffle the image URL schedule before measuring. Sampling is "
            "without replacement until the input list is exhausted."
        ),
    )
    parser.add_argument(
        "--image-url-seed",
        type=int,
        help="Optional seed for reproducible randomized image URL schedules.",
    )
    parser.add_argument(
        "--target",
        choices=["none", "challenge", "five-minute-estimate"],
        default="none",
    )
    parser.add_argument("--projection-multiplier", type=float)
    parser.add_argument("--min-valid-exact", type=int)
    parser.add_argument("--max-average-latency-seconds", type=float)
    parser.add_argument("--max-error-rate", type=float)
    parser.add_argument(
        "--mrscraper-api-key-env",
        help=(
            "Name of an environment variable or repo .env key whose value "
            "should be sent as X-MrScraper-Api-Key. The token is not written "
            "to measurement artifacts."
        ),
    )
    return parser.parse_args()


def resolve_request_headers(
    mrscraper_api_key_env: str | None,
    environ: dict[str, str],
) -> dict[str, str]:
    """Build optional request headers for trusted hosted measurements.

    Args:
        mrscraper_api_key_env: Name of the environment variable containing a
            MrScraper token for the API's trusted override header.
        environ: Environment mapping merged from `.env` and process values.

    Returns:
        Headers to send with each measured request.

    Raises:
        ValueError: If a requested token environment key is unset or empty.
    """

    if mrscraper_api_key_env is None:
        return {}

    token = environ.get(mrscraper_api_key_env, "").strip()
    if not token:
        raise ValueError(f"{mrscraper_api_key_env} is empty or unset")
    return {"X-MrScraper-Api-Key": token}


def resolve_projection_multiplier(args: argparse.Namespace) -> float | None:
    """Resolve the optional hourly projection multiplier.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Projection multiplier, or `None` when no projection should be reported.

    Raises:
        ValueError: If an explicit multiplier is non-positive.
    """

    if args.projection_multiplier is not None:
        if args.projection_multiplier <= 0:
            raise ValueError("--projection-multiplier must be positive")
        return args.projection_multiplier
    if args.target == "five-minute-estimate":
        return FIVE_MINUTE_PROJECTION_MULTIPLIER
    return None


def build_thresholds(
    args: argparse.Namespace,
    projection_multiplier: float | None = None,
) -> Thresholds | None:
    """Build optional pass/fail thresholds from parsed arguments."""

    if args.target == "none" and all(
        value is None
        for value in (
            args.min_valid_exact,
            args.max_average_latency_seconds,
            args.max_error_rate,
        )
    ):
        return None

    if args.target == "challenge":
        default_min_valid = CHALLENGE_MIN_VALID_EXACT
        default_max_latency = CHALLENGE_MAX_AVERAGE_LATENCY_SECONDS
        default_max_error_rate = CHALLENGE_MAX_ERROR_RATE
    elif args.target == "five-minute-estimate":
        multiplier = projection_multiplier or FIVE_MINUTE_PROJECTION_MULTIPLIER
        default_min_valid = math.ceil(CHALLENGE_MIN_VALID_EXACT / multiplier)
        default_max_latency = CHALLENGE_MAX_AVERAGE_LATENCY_SECONDS
        default_max_error_rate = CHALLENGE_MAX_ERROR_RATE
    else:
        default_min_valid = 0
        default_max_latency = float("inf")
        default_max_error_rate = 1.0

    return Thresholds(
        min_valid_exact=(
            args.min_valid_exact
            if args.min_valid_exact is not None
            else default_min_valid
        ),
        max_average_latency_seconds=(
            args.max_average_latency_seconds
            if args.max_average_latency_seconds is not None
            else default_max_latency
        ),
        max_error_rate=(
            args.max_error_rate
            if args.max_error_rate is not None
            else default_max_error_rate
        ),
    )


async def async_main() -> int:
    """Run measurement and write artifacts."""

    args = parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    merged_environ = {**parse_env_file(repo_root / ".env"), **os.environ}
    request_headers = resolve_request_headers(args.mrscraper_api_key_env, merged_environ)
    image_urls = load_image_urls(args.image_url, args.image_url_file)
    image_url_schedule = build_image_url_schedule(
        image_urls,
        args.requests,
        args.randomize_image_urls,
        args.image_url_seed,
    )
    projection_multiplier = resolve_projection_multiplier(args)
    thresholds = build_thresholds(args, projection_multiplier)
    output_dir = args.output_dir or repo_root / ".runtime" / "runs" / f"lens-measure-{safe_timestamp()}"
    output_dir.mkdir(parents=True, exist_ok=True)

    started_at = utc_timestamp()
    wall_started = time.perf_counter()
    results = await run_measurement(
        base_url=args.base_url,
        image_url_schedule=image_url_schedule,
        request_count=args.requests,
        concurrency=args.concurrency,
        rate_per_minute=args.rate_per_minute,
        timeout_seconds=args.timeout_seconds,
        request_headers=request_headers,
    )
    elapsed_seconds = time.perf_counter() - wall_started
    finished_at = utc_timestamp()
    summary = summarize_results(
        results,
        thresholds,
        projection_multiplier,
        elapsed_seconds,
    )
    run_config = {
        "baseUrl": args.base_url,
        "concurrency": args.concurrency,
        "finishedAt": finished_at,
        "imageUrlCount": len(image_urls),
        "imageUrlScheduleHash": hash_url("\n".join(image_url_schedule)),
        "imageUrlSeed": args.image_url_seed,
        "outputDir": str(output_dir),
        "projectionMultiplier": projection_multiplier,
        "providerTokenOverride": bool(request_headers),
        "providerTokenEnv": args.mrscraper_api_key_env if request_headers else None,
        "randomizeImageUrls": args.randomize_image_urls,
        "ratePerMinute": args.rate_per_minute,
        "requestCount": args.requests,
        "startedAt": started_at,
        "target": args.target,
        "timeoutSeconds": args.timeout_seconds,
    }
    artifact = {
        "run": run_config,
        **summary,
    }

    write_json(output_dir / "report.json", artifact)
    write_json(
        output_dir / "verdict.json",
        {
            "metrics": summary["metrics"],
            "observedHourChallengePassed": summary["observedHourChallengePassed"],
            "observedHourEstimate": summary["observedHourEstimate"],
            "passed": summary["passed"],
            "projectedHourEstimate": summary["projectedHourEstimate"],
        },
    )
    write_jsonl(output_dir / "samples.jsonl", results)
    (output_dir / "report.md").write_text(
        render_markdown_report(summary, run_config),
        encoding="utf-8",
    )

    print(f"Measurement artifacts: {output_dir}")
    print(json.dumps(summary["metrics"], indent=2))
    if summary["passed"] is False:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(async_main()))
