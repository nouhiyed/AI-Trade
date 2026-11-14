import unittest
import pandas as pd

from core.scalping_v3 import FuturesScalpingStrategyV3, SpotScalpingStrategyV3


def frames():
    n = 80
    one = pd.DataFrame({
        "open": [100.0] * (n - 1) + [100.1],
        "high": [100.3] * (n - 1) + [100.55],
        "low": [99.9] * (n - 1) + [99.95],
        "close": [100.05] * (n - 1) + [100.45],
        "volume": [1000.0] * (n - 1) + [1250.0],
        "EMA_9": [100.0] * (n - 4) + [100.02, 100.04, 100.06, 100.1],
        "EMA_20": [99.95] * (n - 4) + [99.97, 99.98, 99.99, 100.0],
        "ATR": [0.20] * n,
        "RSI": [54.0] * (n - 1) + [57.0],
        "MACD_hist": [0.02] * (n - 1) + [0.05],
        "BB_lower": [98.0] * n,
        "BB_upper": [102.0] * n,
    })
    five = pd.DataFrame({
        "open": [100.0] * n, "high": [101.0] * n, "low": [99.5] * n,
        "close": [100.5] * n, "EMA_21": [100.0] * n,
        "ATR": [0.50] * n, "ADX": [22.0] * n,
    })
    fifteen = pd.DataFrame({
        "close": [101.0] * n, "EMA_21": [100.5] * n, "EMA_50": [100.0] * n,
    })
    hourly = pd.DataFrame({"close": [105.0] * n, "EMA_200": [100.0] * n})
    four = pd.DataFrame({"close": [104.0] * n, "EMA_200": [100.0] * n})
    return {"1m": one, "5m": five, "15m": fifteen, "1h": hourly, "4h": four}


class V3OnlyStrategyTests(unittest.TestCase):
    def test_futures_v3_returns_cost_adjusted_plan_at_or_above_1_5(self):
        result = FuturesScalpingStrategyV3().analyze(frames())
        self.assertTrue(result["success"], result)
        self.assertEqual(result["strategy_version"], "v3")
        self.assertIn(result["direction"], ("LONG", "SHORT"))
        self.assertGreaterEqual(result["net_reward_risk"], 1.5)
        self.assertEqual(result["max_hold_minutes"], 12)
        self.assertLess(result["stop_loss"], result["entry"])
        self.assertGreater(result["take_profit"], result["entry"])

    def test_spot_v3_is_long_only_and_net_rr_is_at_least_1_5(self):
        result = SpotScalpingStrategyV3().analyze(frames())
        self.assertTrue(result["success"], result)
        self.assertEqual(result["direction"], "LONG")
        self.assertGreaterEqual(result["net_reward_risk"], 1.5)
        self.assertEqual(result["max_hold_minutes"], 15)
        self.assertLess(result["stop_loss"], result["entry"])
        self.assertGreater(result["take_profit"], result["entry"])

    def test_futures_v3_supports_short_setups(self):
        data = frames()
        one = data["1m"]
        one.loc[one.index[-1], ["open", "high", "low", "close"]] = [100.1, 100.2, 99.6, 99.7]
        one.loc[one.index[-1], ["EMA_9", "EMA_20", "RSI", "MACD_hist"]] = [100.0, 100.0, 40.0, -0.05]
        one.loc[one.index[-2], "MACD_hist"] = -0.02
        five = data["5m"]
        five["close"] = 99.5
        five["EMA_21"] = 100.0
        fifteen = data["15m"]
        fifteen["close"] = 99.0
        fifteen["EMA_21"] = 99.5
        fifteen["EMA_50"] = 100.0
        result = FuturesScalpingStrategyV3().analyze(data)
        self.assertTrue(result["success"], result)
        self.assertEqual(result["direction"], "SHORT")
        self.assertGreater(result["stop_loss"], result["entry"])
        self.assertLess(result["take_profit"], result["entry"])
        self.assertGreaterEqual(result["net_reward_risk"], 1.5)

    def test_spot_v3_blocks_deep_bearish_four_hour_context(self):
        data = frames()
        data["4h"]["close"] = 90.0
        data["1h"]["close"] = 90.0
        result = SpotScalpingStrategyV3().analyze(data)
        self.assertFalse(result["success"])
        self.assertIn("Deep 4h", result["reason"])


if __name__ == "__main__":
    unittest.main()
