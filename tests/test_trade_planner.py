import unittest

import pandas as pd

from core.trade_planner import TradePlanner


class TestTradePlanner(unittest.TestCase):
    def setUp(self):
        self.planner = TradePlanner()

    def frame(self, close=100.0, atr=2.0, support=98.2, resistance=110.0):
        return pd.DataFrame([{
            "close": close,
            "atr": atr,
            "support": support,
            "resistance": resistance,
        }])

    def test_long_uses_nearer_valid_structural_stop(self):
        plan = self.planner.create(
            {"symbol": "BTCUSDT", "15m": self.frame()}, "LONG")
        self.assertTrue(plan["success"], plan)
        self.assertAlmostEqual(plan["stop_loss"], 97.9)
        self.assertGreaterEqual(plan["reward_risk"], 1.5)
        self.assertLess(plan["stop_loss"], plan["entry"])
        self.assertGreater(plan["take_profit"], plan["entry"])

    def test_long_keeps_atr_stop_when_structure_is_too_far(self):
        plan = self.planner.create(
            {"symbol": "BTCUSDT",
             "15m": self.frame(support=90.0, resistance=110.0)}, "LONG")
        self.assertTrue(plan["success"], plan)
        self.assertAlmostEqual(plan["stop_loss"], 97.0)

    def test_short_uses_nearer_valid_structural_stop(self):
        plan = self.planner.create(
            {"symbol": "BTCUSDT",
             "15m": self.frame(support=90.0, resistance=101.8)}, "SHORT")
        self.assertTrue(plan["success"], plan)
        self.assertAlmostEqual(plan["stop_loss"], 102.1)
        self.assertLess(plan["take_profit"], plan["entry"])
        self.assertGreater(plan["stop_loss"], plan["entry"])

    def test_prefers_selected_4h_timeframe_when_available(self):
        data = {
            "symbol": "BTCUSDT",
            "15m": self.frame(close=100.0, atr=2.0),
            "4h": self.frame(close=200.0, atr=4.0, support=196.4, resistance=220.0),
        }
        plan = self.planner.create(data, "LONG", preferred_timeframe="4h")
        self.assertTrue(plan["success"], plan)
        self.assertEqual(plan["timeframe"], "4h")
        self.assertAlmostEqual(plan["entry"], 200.0)

    def test_rejects_target_blocked_by_resistance(self):
        plan = self.planner.create(
            {"symbol": "BTCUSDT",
             "15m": self.frame(support=98.0, resistance=102.0)}, "LONG")
        self.assertFalse(plan["success"])
        self.assertIn("Reward/risk", plan["reason"])

    def test_rejects_invalid_minimum_reward_risk(self):
        plan = self.planner.create(
            {"symbol": "BTCUSDT", "15m": self.frame()},
            "LONG", min_reward_risk=float("nan"))
        self.assertFalse(plan["success"])


if __name__ == "__main__":
    unittest.main()
