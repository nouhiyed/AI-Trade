import unittest

from core.market_data_engine import MarketDataEngine


class TestMarketDataEngine(unittest.TestCase):
    def test_build_live_reads_only_requested_domain_from_local_cache(self):
        engine = MarketDataEngine()
        calls = []

        def fake_snapshot(market, symbol, timeframes):
            calls.append((market, symbol, tuple(timeframes)))
            return {"candles": {}, "orderbook": {"available": True},
                    "errors": {}}

        engine.cache.snapshot = fake_snapshot
        engine.binance.fetch_snapshot = lambda **kwargs: self.fail(
            "Live analysis must not call REST fetch_snapshot")
        result = engine.build_live("BTCUSDT", domains=["spot"])

        self.assertEqual(calls, [("spot", "BTCUSDT", tuple(engine.timeframes["spot"]))])
        self.assertEqual(set(result["timeframes"]["futures"]), set())
        self.assertEqual(result["timeframes"]["spot"], {})
        self.assertEqual(result["source"], "binance_websocket_cache")

    def test_build_live_rejects_unknown_domain(self):
        engine = MarketDataEngine()
        with self.assertRaises(ValueError):
            engine.build_live("BTCUSDT", domains=["alpha"])


if __name__ == "__main__":
    unittest.main()
