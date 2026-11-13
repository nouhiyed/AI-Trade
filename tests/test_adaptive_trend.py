import unittest

import pandas as pd

from core.adaptive_trend import AdaptiveTrendStrategy


class AdaptiveTrendTests(unittest.TestCase):
    def setUp(self):
        self.strategy = AdaptiveTrendStrategy()

    def test_generates_long_plan_only_after_aligned_breakout_retest(self):
        n = 210
        hourly = pd.DataFrame({
            "close": [110.0] * n,
            "EMA_50": [105.0 + i * 0.01 for i in range(n)],
            "EMA_200": [100.0] * n,
            "ADX": [25.0] * n,
        })
        rows = []
        for i in range(80):
            rows.append({"open": 99.5, "high": 100.0, "low": 99.0,
                         "close": 99.7, "volume": 100.0, "ATR": 1.0})
        rows[77] = {"open": 100.0, "high": 103.0, "low": 99.8,
                    "close": 102.0, "volume": 180.0, "ATR": 1.0}
        rows[79] = {"open": 100.2, "high": 101.0, "low": 99.9,
                    "close": 100.6, "volume": 120.0, "ATR": 1.0}
        fifteen = pd.DataFrame(rows)
        five = pd.DataFrame([
            {"open": 100.5, "high": 101.0, "low": 100.2, "close": 100.7},
            {"open": 100.7, "high": 101.5, "low": 100.6, "close": 101.2},
            {"open": 101.2, "high": 102.0, "low": 101.0, "close": 101.8},
        ])
        plan = self.strategy.analyze(
            {"symbol": "BTCUSDT", "1h": hourly, "15m": fifteen, "5m": five},
            market="futures",
        )
        self.assertTrue(plan["success"], plan)
        self.assertEqual(plan["direction"], "LONG")
        self.assertLess(plan["stop_loss"], plan["entry"])
        self.assertGreater(plan["take_profit"], plan["entry"])
        self.assertGreaterEqual(plan["net_reward_risk"], 1.5)

    def test_trailing_stop_only_tightens(self):
        self.assertEqual(self.strategy.update_trailing_stop("LONG", 95, 110, 2), 104)
        self.assertEqual(self.strategy.update_trailing_stop("LONG", 106, 110, 2), 106)
        self.assertEqual(self.strategy.update_trailing_stop("SHORT", 105, 90, 2), 96)
        self.assertEqual(self.strategy.update_trailing_stop("SHORT", 94, 90, 2), 94)

    def test_position_size_uses_cash_risk_and_notional_cap(self):
        qty = self.strategy.size_position(10000, 100, 96, 0.0025, 1.0)
        self.assertAlmostEqual(qty, 6.25)
        self.assertLessEqual(qty * 100, 10000)

    def test_rejects_zero_stop_distance(self):
        self.assertEqual(self.strategy.size_position(1000, 100, 100), 0.0)


if __name__ == "__main__":
    unittest.main()
