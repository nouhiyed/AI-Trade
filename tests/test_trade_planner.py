import unittest

import pandas as pd

from core.trade_planner import TradePlanner


class TestTradePlanner(unittest.TestCase):
    def setUp(self):
        self.planner = TradePlanner()

    def frame(self, direction="SHORT", atr=2.0):
        rows = []
        if direction == "SHORT":
            for i in range(100):
                low = 102.0 + i * 0.01
                rows.append({"open": low + 0.12, "high": low + 0.30, "low": low,
                             "close": low + 0.18, "atr": atr, "support": 99.0,
                             "resistance": 104.0})
            rows[80].update({"open": 100.0, "high": 100.5, "low": 99.0, "close": 100.2})
            rows[97].update({"open": 103.4, "high": 103.8, "low": 103.1, "close": 103.5})
            rows[98].update({"open": 103.6, "high": 104.0, "low": 103.2, "close": 103.3})
            rows[99].update({"open": 103.2, "high": 103.3, "low": 102.7, "close": 102.8})
        else:
            for i in range(100):
                low = 96.6 + i * 0.001
                rows.append({"open": low + 0.05, "high": low + 0.20, "low": low,
                             "close": low + 0.10, "atr": atr, "support": 95.0,
                             "resistance": 101.0})
            rows[80].update({"open": 96.0, "high": 96.3, "low": 95.0, "close": 95.8})
            rows[95].update({"open": 100.0, "high": 101.0, "low": 99.5, "close": 100.2})
            rows[97].update({"open": 96.2, "high": 96.8, "low": 96.0, "close": 96.4})
            rows[98].update({"open": 95.6, "high": 96.3, "low": 95.0, "close": 96.0})
            rows[99].update({"open": 96.2, "high": 97.2, "low": 96.1, "close": 97.1})
        return pd.DataFrame(rows)

    def test_short_enters_only_after_bearish_rejection_at_resistance(self):
        plan = self.planner.create({"symbol": "ZECUSDT", "5m": self.frame()}, "SHORT")
        self.assertTrue(plan["success"], plan)
        self.assertLess(plan["take_profit"], plan["entry"])
        self.assertGreater(plan["stop_loss"], plan["resistance"])
        self.assertIn("Bearish rejection", plan["entry_confirmation"])
        self.assertGreaterEqual(plan["net_reward_risk"], 1.5)

    def test_long_enters_only_after_bullish_rejection_at_support(self):
        plan = self.planner.create({"symbol": "BTCUSDT", "5m": self.frame("LONG")}, "LONG")
        self.assertTrue(plan["success"], plan)
        self.assertGreater(plan["take_profit"], plan["entry"])
        self.assertLess(plan["stop_loss"], plan["support"])
        self.assertIn("Bullish rejection", plan["entry_confirmation"])
        self.assertGreaterEqual(plan["net_reward_risk"], 1.5)

    def test_short_without_rejection_is_rejected(self):
        frame = self.frame()
        frame.loc[99, ["open", "high", "low", "close"]] = [103.2, 104.0, 103.0, 103.8]
        plan = self.planner.create({"symbol": "ZECUSDT", "5m": frame}, "SHORT")
        self.assertFalse(plan["success"])
        self.assertTrue("follow-through" in plan["reason"].lower() or "rejection" in plan["reason"].lower())

    def test_short_is_blocked_after_resistance_breakout_even_if_price_falls_back(self):
        frame = self.frame()
        frame.loc[97, ["open", "high", "low", "close"]] = [104.8, 105.6, 104.5, 105.4]
        plan = self.planner.create({"symbol": "ZECUSDT", "5m": frame}, "SHORT")
        self.assertFalse(plan["success"])
        self.assertIn("breakout", plan["reason"].lower())

    def test_short_without_resistance_is_rejected_not_given_fake_atr_stop(self):
        frame = self.frame()
        frame["resistance"] = None
        frame.loc[95:, "high"] = [103.8, 103.8, 103.8, 103.8, 103.8]
        frame.loc[99, ["open", "high", "low", "close"]] = [103.8, 103.8, 103.6, 103.8]
        plan = self.planner.create({"symbol": "ZECUSDT", "5m": frame}, "SHORT")
        self.assertFalse(plan["success"])
        self.assertIn("resistance", plan["reason"].lower())

    def test_rejects_target_that_does_not_cover_costs(self):
        frame = self.frame()
        frame["support"] = 102.9
        frame["resistance"] = 105.0
        frame.loc[:, "low"] = 103.2
        frame.loc[:, "high"] = 103.4
        frame.loc[:, "open"] = 103.3
        frame.loc[:, "close"] = 103.35
        frame.loc[95, ["open", "high", "low", "close"]] = [103.5, 105.0, 103.3, 104.0]
        frame.loc[98, ["open", "high", "low", "close"]] = [104.5, 105.0, 103.3, 104.0]
        frame.loc[99, ["open", "high", "low", "close"]] = [103.8, 103.9, 103.2, 103.25]
        plan = self.planner.create({"symbol": "ZECUSDT", "5m": frame}, "SHORT")
        self.assertFalse(plan["success"])
        self.assertTrue("fees" in plan["reason"].lower() or "reward/risk" in plan["reason"].lower())

    def test_cannot_lower_minimum_net_reward_risk_below_1_5(self):
        plan = self.planner.create(
            {"symbol": "BTCUSDT", "5m": self.frame()},
            "SHORT", min_reward_risk=1.0)
        self.assertFalse(plan["success"])
        self.assertIn("1.5", plan["reason"])

    def test_rejects_invalid_minimum_reward_risk(self):
        plan = self.planner.create(
            {"symbol": "BTCUSDT", "5m": self.frame()},
            "SHORT", min_reward_risk=float("nan"))
        self.assertFalse(plan["success"])


if __name__ == "__main__":
    unittest.main()
