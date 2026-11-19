import time
import unittest
from unittest.mock import Mock

import pandas as pd

from core.binance_candle_cache import BinanceCandleCache


class TestBinanceCandleCache(unittest.TestCase):
    def setUp(self):
        self.cache = BinanceCandleCache(market_feed=Mock())
        rows = []
        base = pd.Timestamp("2026-11-19T00:00:00Z")
        for index in range(2400):
            opened = base + pd.Timedelta(minutes=5 * index)
            rows.append({
                "open_time": opened, "close_time": opened + pd.Timedelta(minutes=5) - pd.Timedelta(milliseconds=1),
                "open": 100 + index, "high": 102 + index,
                "low": 99 + index, "close": 101 + index,
                "volume": 2.0, "quote_volume": 200.0, "trades": 3,
                "taker_buy_base": 1.0, "taker_buy_quote": 100.0,
                "is_closed": True,
            })
        self.cache._candles[("futures", "BTCUSDT", "5m")] = pd.DataFrame(rows)

    def test_fifteen_minute_and_hour_bars_are_aggregated_from_five_minute(self):
        fifteen = self.cache.get_frame("futures", "BTCUSDT", "15m")
        hourly = self.cache.get_frame("futures", "BTCUSDT", "1h")
        self.assertEqual(len(fifteen), 800)
        self.assertEqual(len(hourly), 200)
        self.assertEqual(fifteen.iloc[0]["open"], 100)
        self.assertEqual(fifteen.iloc[0]["close"], 103)
        self.assertEqual(fifteen.iloc[0]["high"], 104)
        self.assertEqual(fifteen.iloc[0]["low"], 99)
        self.assertEqual(fifteen.iloc[0]["volume"], 6.0)
        self.assertEqual(hourly.iloc[0]["volume"], 24.0)

    def test_websocket_updates_only_closed_candles_and_replaces_duplicate(self):
        self.cache._candles[("spot", "ETHUSDT", "5m")] = pd.DataFrame([{
            "open_time": pd.Timestamp("2026-11-19T00:00:00Z"),
            "close_time": pd.Timestamp("2026-11-19T00:04:59Z"),
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
            "volume": 1.0, "is_closed": True,
        }])
        base_ms = int(pd.Timestamp("2026-11-19T00:00:00Z").timestamp() * 1000)
        open_kline = {"t": base_ms, "T": base_ms + 299999, "o": "100",
                      "h": "102", "l": "99", "c": "101", "v": "2",
                      "q": "200", "n": 4, "V": "1", "Q": "100",
                      "x": False, "i": "5m"}
        self.cache._store_kline("spot", "ETHUSDT", "5m", open_kline)
        self.assertEqual(len(self.cache.get_frame("spot", "ETHUSDT", "5m")), 1)
        open_kline["x"] = True
        self.cache._store_kline("spot", "ETHUSDT", "5m", open_kline)
        frame = self.cache.get_frame("spot", "ETHUSDT", "5m")
        self.assertEqual(len(frame), 1)
        self.assertEqual(float(frame.iloc[0]["close"]), 101.0)

    def test_streamed_quote_is_available_without_rest(self):
        self.cache._quotes[("futures", "BTCUSDT")] = {
            "bid": 100.0, "ask": 101.0, "mid_price": 100.5,
            "received_at": time.time()}
        self.assertEqual(self.cache.get_quote("futures", "BTCUSDT")["ask"], 101.0)


if __name__ == "__main__":
    unittest.main()
