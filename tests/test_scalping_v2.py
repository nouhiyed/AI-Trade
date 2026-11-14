import unittest
import pandas as pd

from core.scalping_v2 import FuturesScalpingStrategyV2, SpotScalpingStrategyV2


def strong_bull_frames():
    n = 80
    five = pd.DataFrame({
        "open": [100.0] * (n - 1) + [100.0],
        "high": [100.45] * (n - 1) + [100.95],
        "low": [99.95] * (n - 1) + [100.05],
        "close": [100.1] * (n - 1) + [100.8],
        "volume": [1000.0] * (n - 1) + [1300.0],
        "EMA_9": [100.0] * (n - 4) + [100.1, 100.2, 100.3, 100.4],
        "EMA_21": [99.8] * (n - 4) + [99.9, 100.0, 100.05, 100.1],
        "ATR": [0.5] * n,
        "RSI": [55.0] * (n - 1) + [58.0],
        "MACD_hist": [0.25] * (n - 1) + [0.45],
        "ADX": [23.0] * n,
        "BB_lower": [98.0] * n,
        "BB_upper": [102.0] * n,
    })
    fifteen = pd.DataFrame({
        "close": [102.0] * n,
        "EMA_21": [101.0] * (n - 4) + [101.1, 101.2, 101.3, 101.4],
        "EMA_50": [100.0] * n,
        "ADX": [25.0] * n,
    })
    hourly = pd.DataFrame({
        "close": [105.0] * n,
        "EMA_200": [100.0] * n,
    })
    four = pd.DataFrame({
        "close": [106.0] * n,
        "EMA_200": [100.0] * n,
    })
    return {"5m": five, "15m": fifteen, "1h": hourly, "4h": four}


class ScalpingV2Tests(unittest.TestCase):
    def test_futures_v2_requires_confirmed_trend_pullback(self):
        result = FuturesScalpingStrategyV2().analyze(
            strong_bull_frames(), {"total_adverse_rate": 0.00015}
        )
        self.assertTrue(result["success"], result)
        self.assertEqual(result["strategy_version"], "v2")
        self.assertEqual(result["setup"], "TREND_PULLBACK")
        self.assertEqual(result["direction"], "LONG")

    def test_spot_v2_is_long_only_and_uses_four_hour_guard(self):
        data = strong_bull_frames()
        result = SpotScalpingStrategyV2().analyze(
            data, {"total_adverse_rate": 0.00015}
        )
        self.assertTrue(result["success"], result)
        self.assertEqual(result["direction"], "LONG")
        data["4h"]["close"] = 90.0
        blocked = SpotScalpingStrategyV2().analyze(
            data, {"total_adverse_rate": 0.00015}
        )
        self.assertFalse(blocked["success"])
        self.assertIn("4h trend filter", blocked["reason"])

    def test_futures_v2_rejects_weak_momentum(self):
        data = strong_bull_frames()
        data["5m"].loc[data["5m"].index[-1], "MACD_hist"] = -0.1
        result = FuturesScalpingStrategyV2().analyze(
            data, {"total_adverse_rate": 0.00015}
        )
        self.assertFalse(result["success"])


if __name__ == "__main__":
    unittest.main()
