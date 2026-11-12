import unittest
from unittest.mock import patch

import requests

from core.binance_market_data import BinanceMarketData


class TestBinanceBookTicker(unittest.TestCase):

    def setUp(self):
        self.client = BinanceMarketData()

    def test_spot_book_ticker(self):
        response = {"bidPrice": "100", "askPrice": "101"}

        with patch.object(self.client, "_request", return_value=response) as req:
            result = self.client.fetch_book_ticker("spot", "btcusdt")

        req.assert_called_once_with(
            "spot", "/api/v3/ticker/bookTicker", {"symbol": "BTCUSDT"}
        )
        self.assertEqual(result["bid"], 100)
        self.assertEqual(result["ask"], 101)
        self.assertEqual(result["spread"], 1)
        self.assertEqual(result["mid_price"], 100.5)
        self.assertAlmostEqual(result["spread_percent"], 1 / 100.5 * 100)
        self.assertEqual(result["source"], "binance_rest")

    def test_futures_book_ticker(self):
        response = {"bidPrice": "200", "askPrice": "200.5"}

        with patch.object(self.client, "_request", return_value=response) as req:
            result = self.client.fetch_book_ticker("futures", "ETHUSDT")

        req.assert_called_once_with(
            "futures", "/fapi/v1/ticker/bookTicker", {"symbol": "ETHUSDT"}
        )
        self.assertEqual(result["market"], "futures")
        self.assertEqual(result["spread"], 0.5)

    def test_fetch_candles_passes_historical_time_bounds(self):
        raw = [[
            1700000000000, "100", "102", "99", "101", "10",
            1700000059999, "1000", 5, "4", "400", "0"
        ], [
            1700000060000, "101", "103", "100", "102", "11",
            1700000119999, "1100", 6, "5", "500", "0"
        ]]
        with patch.object(self.client, "_request", return_value=raw) as req:
            frame = self.client.fetch_candles(
                "spot", "BTCUSDT", "1m", limit=2,
                closed_only=False, start_time=1700000000000,
                end_time=1700000120000,
            )
        params = req.call_args.args[2]
        self.assertEqual(params["startTime"], 1700000000000)
        self.assertEqual(params["endTime"], 1700000120000)
        self.assertEqual(len(frame), 2)


    def test_fallback_hosts_share_one_total_request_budget(self):
        client = BinanceMarketData(timeout=2, total_timeout=2)
        with patch("core.binance_market_data.time.monotonic",
                   side_effect=[0.0, 0.0, 2.1]):
            with patch.object(client.session, "get",
                              side_effect=requests.Timeout("host timed out")) as get:
                with self.assertRaisesRegex(RuntimeError, "time budget exhausted"):
                    client._request("futures", "/fapi/v1/time", {})
        self.assertEqual(get.call_count, 1)

    def test_rejects_invalid_market(self):
        with self.assertRaises(ValueError):
            self.client.fetch_book_ticker("margin", "BTCUSDT")

    def test_rejects_missing_prices(self):
        with patch.object(self.client, "_request", return_value={"bidPrice": "100"}):
            with self.assertRaises(RuntimeError):
                self.client.fetch_book_ticker("spot", "BTCUSDT")

    def test_rejects_invalid_or_crossed_prices(self):
        invalid_responses = [
            {"bidPrice": "0", "askPrice": "1"},
            {"bidPrice": "NaN", "askPrice": "2"},
            {"bidPrice": "102", "askPrice": "101"},
        ]

        for response in invalid_responses:
            with self.subTest(response=response):
                with patch.object(
                    self.client, "_request", return_value=response
                ):
                    with self.assertRaises(RuntimeError):
                        self.client.fetch_book_ticker("spot", "BTCUSDT")


if __name__ == "__main__":
    unittest.main()
