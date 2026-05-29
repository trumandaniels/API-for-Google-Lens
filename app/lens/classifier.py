"""Classify upstream Google HTML before returning it as API output."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re


class HtmlVerdict(StrEnum):
    """Possible classifications for upstream Google HTML.

    Example:
        >>> HtmlVerdict.EXACT_MATCH.value
        'exact_match'
    """

    EXACT_MATCH = "exact_match"
    NO_MATCH = "no_match"
    BOT_BLOCK = "bot_block"
    GOOGLE_ERROR = "google_error"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class HtmlClassification:
    """Result of classifying an upstream Google HTML response.

    Attributes:
        verdict: High-level response classification.
        reason: Short diagnostic reason suitable for logs and tests.

    Example:
        >>> HtmlClassification(HtmlVerdict.UNKNOWN, "missing markers").reason
        'missing markers'
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
    "Error 403",
    "Bad Request",
    "Forbidden",
    "The requested URL was not found on this server",
)

EXACT_MATCH_MARKERS = (
    "Exact matches",
    "Visual matches",
    "Search Results",
)

NO_MATCH_MARKERS = (
    "No matches for your search",
    "try changing the search area or submitting another image",
    "Tidak ada kecocokan untuk penelusuran Anda",
    "coba ubah area penelusuran atau kirim gambar lain",
)

EXACT_MATCH_TAB_LABELS = frozenset(
    {
        "exact matches",
        "kecocokan persis",
    }
)

NON_EXACT_SELECTED_TAB_LABELS = frozenset(
    {
        "all",
        "semua",
        "visual matches",
    }
)

SELECTED_TAB_PATTERN = re.compile(
    r'aria-current="page"[^>]*selected[^>]*class="mXwfNd"[^>]*>\s*'
    r'<span[^>]*class="R1QWuf"[^>]*>(?P<label>[^<]+)</span>',
    re.IGNORECASE,
)


def contains_no_match_empty_state(html: str) -> bool:
    """Return whether HTML contains a Google Lens no-result empty state.

    Args:
        html: Raw Google HTML body.

    Returns:
        `True` when any known localized no-match marker is present.

    Example:
        >>> contains_no_match_empty_state("<h2>No matches for your search</h2>")
        True
    """
    normalized_html = html.lower()
    return any(marker.lower() in normalized_html for marker in NO_MATCH_MARKERS)


def selected_lens_tab_label(html: str) -> str | None:
    """Return the selected Lens tab label from Google HTML, if present.

    Args:
        html: Raw Google Lens/Search HTML.

    Returns:
        Lowercase selected tab label, or `None` when the page shape does not
        include the expected selected-tab marker.

    Example:
        >>> selected_lens_tab_label('<div aria-current="page" selected="" class="mXwfNd"><span class="R1QWuf">Semua</span></div>')
        'semua'
    """
    selected_tab = SELECTED_TAB_PATTERN.search(html)
    if selected_tab is None:
        return None
    return selected_tab.group("label").strip().lower()


def classify_google_html(html: str, final_url: str = "") -> HtmlClassification:
    """Classify an upstream Google response body.

    Args:
        html: Raw upstream response body.
        final_url: Final URL after redirects, when available.

    Returns:
        Classification verdict and reason.

    Example:
        >>> result = classify_google_html(
        ...     "<html>Exact matches Search Results</html>",
        ...     "https://www.google.com/search?udm=48",
        ... )
        >>> result.verdict.value
        'exact_match'
    """
    if not html.strip():
        return HtmlClassification(HtmlVerdict.UNKNOWN, "empty HTML body")

    normalized_html = html.lower()
    lower_url = final_url.lower()
    if "google.com/sorry" in lower_url:
        return HtmlClassification(HtmlVerdict.BOT_BLOCK, "Google sorry URL")

    if any(marker.lower() in normalized_html for marker in BOT_BLOCK_MARKERS):
        return HtmlClassification(HtmlVerdict.BOT_BLOCK, "bot-block marker present")

    if any(marker.lower() in normalized_html for marker in GOOGLE_ERROR_MARKERS):
        return HtmlClassification(HtmlVerdict.GOOGLE_ERROR, "Google error marker present")

    label = selected_lens_tab_label(html)
    if label is not None:
        if label in EXACT_MATCH_TAB_LABELS:
            if contains_no_match_empty_state(html):
                return HtmlClassification(
                    HtmlVerdict.EXACT_MATCH,
                    "Exact Match tab selected with no matches",
                )
            return HtmlClassification(HtmlVerdict.EXACT_MATCH, "Exact Match tab selected")
        if label in NON_EXACT_SELECTED_TAB_LABELS:
            return HtmlClassification(HtmlVerdict.UNKNOWN, f"{label.title()} tab selected")

    if "udm=48" in lower_url and "exact matches" in normalized_html and "search results" in normalized_html:
        return HtmlClassification(HtmlVerdict.EXACT_MATCH, "Exact Match URL and markers present")

    if "udm=48" in lower_url and contains_no_match_empty_state(html):
        return HtmlClassification(
            HtmlVerdict.EXACT_MATCH,
            "Exact Match URL has no matches",
        )

    if contains_no_match_empty_state(html):
        return HtmlClassification(HtmlVerdict.NO_MATCH, "No-match marker present")

    return HtmlClassification(HtmlVerdict.UNKNOWN, "Exact Match markers absent")
