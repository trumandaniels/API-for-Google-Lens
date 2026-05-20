from __future__ import annotations

import unittest

from app.errors import (
    BotBlockError,
    ExactMatchNotFoundError,
    ProviderCreditsExhaustedError,
    UpstreamRequestError,
)
from app.lens.direct import DirectLensResponse
from app.lens.service import (
    PROVIDER_CREDIT_ERROR_DETAIL,
    GoogleLensService,
    is_provider_credit_error,
)
from app.models import ImageUrl, ProviderApiToken
from app.throttling import AsyncConcurrencyLimiter


class StaticLensClient:
    """Test double that returns one configured provider response."""

    def __init__(self, response: DirectLensResponse) -> None:
        self.response = response

    async def fetch_exact_match_html(
        self,
        image_url: ImageUrl,
        token_override: ProviderApiToken | None = None,
    ) -> DirectLensResponse:
        """Return the configured response without network work."""
        return self.response


class ProviderCreditErrorTests(unittest.IsolatedAsyncioTestCase):
    def test_detects_provider_credit_exhaustion_marker(self) -> None:
        self.assertTrue(is_provider_credit_error(402, ""))
        self.assertTrue(is_provider_credit_error(400, "Out of Proxy Credits"))
        self.assertTrue(is_provider_credit_error(400, '{"error":"insufficient credits"}'))
        self.assertFalse(is_provider_credit_error(200, "<html>Exact matches</html>"))

    async def test_service_raises_specific_provider_credit_error(self) -> None:
        service = GoogleLensService(
            client=StaticLensClient(
                DirectLensResponse(
                    html="Out of Proxy Credits",
                    final_url="https://api.mrscraper.com",
                    status_code=402,
                )
            ),  # type: ignore[arg-type]
            limiter=AsyncConcurrencyLimiter(1),
        )

        with self.assertRaises(ProviderCreditsExhaustedError) as context:
            await service.fetch_exact_match_html(
                ImageUrl.parse("https://example.com/image.jpg")
            )

        self.assertEqual(context.exception.message, PROVIDER_CREDIT_ERROR_DETAIL)

    async def test_service_maps_provider_rate_limit_to_bot_block(self) -> None:
        service = GoogleLensService(
            client=StaticLensClient(
                DirectLensResponse(
                    html="Too Many Requests",
                    final_url="https://api.mrscraper.com",
                    status_code=429,
                )
            ),  # type: ignore[arg-type]
            limiter=AsyncConcurrencyLimiter(1),
        )

        with self.assertRaises(BotBlockError) as context:
            await service.fetch_exact_match_html(
                ImageUrl.parse("https://example.com/image.jpg")
            )

        self.assertIn("rate limited", context.exception.message)

    async def test_service_reports_upstream_status_code_in_generic_failure(self) -> None:
        service = GoogleLensService(
            client=StaticLensClient(
                DirectLensResponse(
                    html="Internal Server Error",
                    final_url="https://api.mrscraper.com",
                    status_code=503,
                )
            ),  # type: ignore[arg-type]
            limiter=AsyncConcurrencyLimiter(1),
        )

        with self.assertRaises(UpstreamRequestError) as context:
            await service.fetch_exact_match_html(
                ImageUrl.parse("https://example.com/image.jpg")
            )

        self.assertIn("HTTP 503", context.exception.message)

    async def test_service_rejects_exact_match_empty_state(self) -> None:
        service = GoogleLensService(
            client=StaticLensClient(
                DirectLensResponse(
                    html=(
                        '<div aria-current="page" selected="" class="mXwfNd">'
                        '<span class="R1QWuf">Exact matches</span></div>'
                        "<h2>No matches for your search</h2>"
                    ),
                    final_url="https://www.google.com/search?udm=48",
                    status_code=200,
                )
            ),  # type: ignore[arg-type]
            limiter=AsyncConcurrencyLimiter(1),
        )

        with self.assertRaises(ExactMatchNotFoundError) as context:
            await service.fetch_exact_match_html(
                ImageUrl.parse("https://example.com/image.jpg")
            )

        self.assertIn("no matches", context.exception.message)


if __name__ == "__main__":
    unittest.main()
