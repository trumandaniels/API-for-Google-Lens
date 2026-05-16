from __future__ import annotations

import unittest

from app.errors import (
    BotBlockError,
    MalformedImageUrlError,
    ProviderCreditsExhaustedError,
    UpstreamTimeoutError,
    to_http_error,
)


class ErrorMappingTests(unittest.TestCase):
    def test_malformed_url_maps_to_bad_request(self) -> None:
        exception = to_http_error(MalformedImageUrlError("bad URL"))

        self.assertEqual(exception.status_code, 400)
        self.assertEqual(exception.detail, "bad URL")

    def test_timeout_maps_to_gateway_timeout(self) -> None:
        exception = to_http_error(UpstreamTimeoutError("timeout"))

        self.assertEqual(exception.status_code, 504)

    def test_bot_block_maps_to_too_many_requests(self) -> None:
        exception = to_http_error(BotBlockError("blocked"))

        self.assertEqual(exception.status_code, 429)

    def test_provider_credits_exhausted_maps_to_payment_required(self) -> None:
        exception = to_http_error(ProviderCreditsExhaustedError("credits exhausted"))

        self.assertEqual(exception.status_code, 402)
        self.assertEqual(exception.detail, "credits exhausted")


if __name__ == "__main__":
    unittest.main()
