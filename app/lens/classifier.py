"""Classify upstream Google HTML before returning it as API output."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class HtmlVerdict(StrEnum):
    """Possible classifications for upstream Google HTML."""

    EXACT_MATCH = "exact_match"
    BOT_BLOCK = "bot_block"
    GOOGLE_ERROR = "google_error"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class HtmlClassification:
    """Result of classifying an upstream Google HTML response.

    Attributes:
        verdict: High-level response classification.
        reason: Short diagnostic reason suitable for logs and tests.
    """

    verdict: HtmlVerdict
    reason: str


BOT_BLOCK_MARKERS = (
    "Our systems have detected unusual traffic",
    "/sorry/index",
    "g-recaptcha",
    "recaptcha",
)

GOOGLE_ERROR_MARKERS = (
    "Error 400",
    "Bad Request",
    "The requested URL was not found on this server",
)

EXACT_MATCH_MARKERS = (
    "Exact matches",
    "Visual matches",
    "Google Lens",
)


def classify_google_html(html: str, final_url: str = "") -> HtmlClassification:
    """Classify an upstream Google response body.

    Args:
        html: Raw upstream response body.
        final_url: Final URL after redirects, when available.

    Returns:
        Classification verdict and reason.
    """
    if not html.strip():
        return HtmlClassification(HtmlVerdict.UNKNOWN, "empty HTML body")

    lower_url = final_url.lower()
    if "google.com/sorry" in lower_url:
        return HtmlClassification(HtmlVerdict.BOT_BLOCK, "Google sorry URL")

    if any(marker.lower() in html.lower() for marker in BOT_BLOCK_MARKERS):
        return HtmlClassification(HtmlVerdict.BOT_BLOCK, "bot-block marker present")

    if any(marker.lower() in html.lower() for marker in GOOGLE_ERROR_MARKERS):
        return HtmlClassification(HtmlVerdict.GOOGLE_ERROR, "Google error marker present")

    if all(marker.lower() in html.lower() for marker in ("exact matches", "google lens")):
        return HtmlClassification(HtmlVerdict.EXACT_MATCH, "Exact Match markers present")

    return HtmlClassification(HtmlVerdict.UNKNOWN, "Exact Match markers absent")

