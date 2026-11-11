import unittest

from core.market_data_engine import MarketDataEngine


class TestMarketDataEngine(unittest.TestCase):
    def test_build_live_fetches_only_requested_domain(self):
        engine = MarketDataEngine()
        calls = []

        def fake_snapshot(market, symbol, timeframes, candle_limit, orderbook_limit):
            calls.append((market, tuple(timeframes)))
            return {
                "candles": {},
                "orderbook": {"available": True},
                "errors": {},
            }

        engine.binance.fetch_snapshot = fake_snapshot
        result = engine.build_live("BTCUSDT", domains=["spot"])

        self.assertEqual([market for market, _ in calls], ["spot"])
        self.assertEqual(set(result["timeframes"]["futures"]), set())
        self.assertEqual(result["timeframes"]["spot"], {})
        self.assertEqual(calls[0][1], tuple(engine.timeframes["spot"]))

    def test_build_live_rejects_unknown_domain(self):
        engine = MarketDataEngine()
        with self.assertRaises(ValueError):
            engine.build_live("BTCUSDT", domains=["alpha"])


if __name__ == "__main__":
    unittest.main()
