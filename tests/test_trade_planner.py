import unittest

import pandas as pd

from core.trade_planner import TradePlanner


class TestTradePlanner(unittest.TestCase):
    def setUp(self):
        self.planner = TradePlanner()

    def frame(self, direction="SHORT", atr=2.0):
        rows = []
        if direction == "SHORT":
            for _ in range(100):
                rows.append({"open": 103.05, "high": 103.2, "low": 103.0,
                             "close": 103.1, "atr": atr, "support": 99.0,
                             "resistance": 105.0})
            rows[80].update({"open": 100.0, "high": 100.5, "low": 99.0, "close": 100.2})
            rows[95].update({"open": 103.0, "high": 105.0, "low": 102.8, "close": 104.0})
            rows[98].update({"open": 104.0, "high": 105.0, "low": 103.2, "close": 104.5})
            rows[99].update({"open": 104.4, "high": 104.9, "low": 103.0, "close": 103.5})
        else:
            for _ in range(100):
                rows.append({"open": 96.95, "high": 97.1, "low": 96.8,
                             "close": 96.9, "atr": atr, "support": 95.0,
                             "resistance": 101.0})
            rows[80].update({"open": 96.0, "high": 96.3, "low": 95.0, "close": 95.8})
            rows[95].update({"open": 100.0, "high": 101.0, "low": 99.5, "close": 100.2})
            rows[98].update({"open": 96.0, "high": 97.0, "low": 95.0, "close": 95.5})
            rows[99].update({"open": 95.6, "high": 96.8, "low": 95.0, "close": 96.5})
        return pd.DataFrame(rows)

    def test_short_enters_only_after_bearish_rejection_at_resistance(self):
        plan = self.planner.create({"symbol": "ZECUSDT", "5m": self.frame()}, "SHORT")
        self.assertTrue(plan["success"], plan)
        self.assertLess(plan["take_profit"], plan["entry"])
        self.assertGreater(plan["stop_loss"], plan["resistance"])
        self.assertIn("Bearish rejection", plan["entry_confirmation"])
        self.assertGreater(plan["net_reward_risk"], 1.0)

    def test_long_enters_only_after_bullish_rejection_at_support(self):
        plan = self.planner.create({"symbol": "BTCUSDT", "5m": self.frame("LONG")}, "LONG")
        self.assertTrue(plan["success"], plan)
        self.assertGreater(plan["take_profit"], plan["entry"])
        self.assertLess(plan["stop_loss"], plan["support"])
        self.assertIn("Bullish rejection", plan["entry_confirmation"])

    def test_short_without_rejection_is_rejected(self):
        frame = self.frame()
        frame.loc[99, ["open", "high", "low", "close"]] = [103.2, 104.0, 103.0, 103.8]
        plan = self.planner.create({"symbol": "ZECUSDT", "5m": frame}, "SHORT")
        self.assertFalse(plan["success"])
        self.assertIn("rejection candle", plan["reason"])

    def test_short_without_resistance_is_rejected_not_given_fake_atr_stop(self):
        frame = self.frame()
        frame["resistance"] = None
        frame.loc[95:, "high"] = [103.2, 103.2, 103.2, 103.2, 103.2]
        frame.loc[99, ["open", "high", "low", "close"]] = [103.1, 103.2, 102.8, 102.9]
        plan = self.planner.create({"symbol": "ZECUSDT", "5m": frame}, "SHORT")
        self.assertFalse(plan["success"])
        self.assertIn("resistance", plan["reason"].lower())

    def test_rejects_target_that_does_not_cover_costs(self):
        frame = self.frame()
        frame["support"] = 103.4
        frame.loc[80, ["open", "high", "low", "close"]] = [103.45, 103.5, 103.4, 103.45]
        plan = self.planner.create({"symbol": "ZECUSDT", "5m": frame}, "SHORT")
        self.assertFalse(plan["success"])
        self.assertTrue("fees" in plan["reason"].lower() or "reward/risk" in plan["reason"].lower())

    def test_rejects_invalid_minimum_reward_risk(self):
        plan = self.planner.create(
            {"symbol": "BTCUSDT", "5m": self.frame()},
            "SHORT", min_reward_risk=float("nan"))
        self.assertFalse(plan["success"])


if __name__ == "__main__":
    unittest.main()
