import unittest
from unittest.mock import patch

from core.binance_market_data import BinanceMarketData


class FakeResponse:
    def __init__(self, status, payload=None, headers=None):
        self.status_code = status
        self._payload = payload or {"ok": True}
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            from requests import HTTPError
            raise HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class BinanceRateLimitTests(unittest.TestCase):
    def setUp(self):
        self.client = BinanceMarketData(timeout=2, total_timeout=2)

    def test_418_stops_fallback_hosts_immediately(self):
        with patch.object(
            self.client.session, "get", return_value=FakeResponse(418)
        ) as get_request, patch(
            "core.binance_market_data.time.sleep"
        ), patch(
            "core.binance_market_data._BINANCE_LAST_REQUEST_AT", 0.0
        ):
            with self.assertRaisesRegex(RuntimeError, "HTTP 418"):
                self.client._request("spot", "/api/v3/test", {})
        self.assertEqual(get_request.call_count, 1)

    def test_429_waits_and_retries_once_on_the_same_host(self):
        responses = [
            FakeResponse(429, headers={"Retry-After": "0"}),
            FakeResponse(200, payload={"ok": True}),
        ]
        with patch.object(
            self.client.session, "get", side_effect=responses
        ) as get_request, patch(
            "core.binance_market_data.time.sleep"
        ), patch(
            "core.binance_market_data._BINANCE_LAST_REQUEST_AT", 0.0
        ):
            result = self.client._request("spot", "/api/v3/test", {})
        self.assertEqual(result, {"ok": True})
        self.assertEqual(get_request.call_count, 2)


if __name__ == "__main__":
    unittest.main()
