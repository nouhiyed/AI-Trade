import unittest

import pandas as pd

from core.adaptive_trend import AdaptiveTrendStrategy
from core.market_regime import MarketRegimeEngine


class MarketRegimeTests(unittest.TestCase):
    def frame(self, direction="bull", adx=30.0, shock=False):
        n = 210
        ema50 = [105.0 + i * 0.2 for i in range(n)]
        ema200 = [100.0] * n
        close = [110.0] * n
        plus, minus = [30.0] * n, [10.0] * n
        if direction == "bear":
            ema50 = [95.0 - i * 0.2 for i in range(n)]
            ema200, close = [100.0] * n, [90.0] * n
            plus, minus = [10.0] * n, [30.0] * n
        if direction == "transition":
            ema50 = [100.1 + i * 0.005 for i in range(n)]
        atr = [2.0] * n
        if shock:
            atr[-1] = 6.0
        return pd.DataFrame({
            "close": close, "EMA_50": ema50, "EMA_200": ema200,
            "ADX": [adx] * n, "ATR": atr, "PLUS_DI": plus, "MINUS_DI": minus,
        })

    def test_detects_bullish_and_bearish_trends(self):
        self.assertEqual(MarketRegimeEngine.classify(self.frame("bull"))["regime"], "BULLISH")
        self.assertEqual(MarketRegimeEngine.classify(self.frame("bear"))["regime"], "BEARISH")

    def test_detects_range_transition_and_volatility_shock(self):
        self.assertEqual(MarketRegimeEngine.classify(self.frame(adx=12))["regime"], "RANGE")
        self.assertEqual(MarketRegimeEngine.classify(self.frame("transition"))["regime"], "TRANSITION")
        shock = MarketRegimeEngine.classify(self.frame(shock=True))
        self.assertEqual(shock["regime"], "HIGH_VOLATILITY")
        self.assertFalse(shock["allow_trade"])

    def test_weak_trend_is_distinguished_from_strong(self):
        result = MarketRegimeEngine.classify(self.frame(adx=20))
        self.assertEqual(result["strength"], "WEAK")
        self.assertTrue(result["allow_trade"])


class AdaptiveTrendTests(unittest.TestCase):
    def setUp(self):
        self.strategy = AdaptiveTrendStrategy()

    def market_frames(self):
        n = 210
        hourly = pd.DataFrame({
            "close": [110.0] * n,
            "EMA_50": [105.0 + i * 0.2 for i in range(n)],
            "EMA_200": [100.0] * n, "ADX": [30.0] * n,
            "ATR": [2.0] * n, "PLUS_DI": [30.0] * n, "MINUS_DI": [10.0] * n,
        })
        rows = []
        for _ in range(80):
            rows.append({"open": 99.5, "high": 100.0, "low": 99.0,
                         "close": 99.7, "volume": 100.0, "ATR": 1.0})
        rows[77] = {"open": 100.0, "high": 102.0, "low": 99.6,
                    "close": 101.2, "volume": 180.0, "ATR": 1.0}
        rows[78] = {"open": 100.1, "high": 100.8, "low": 100.0,
                    "close": 100.4, "volume": 110.0, "ATR": 1.0}
        rows[79] = {"open": 100.2, "high": 101.0, "low": 99.9,
                    "close": 100.6, "volume": 120.0, "ATR": 1.0}
        fifteen = pd.DataFrame(rows)
        five = pd.DataFrame([
            {"open": 100.5, "high": 101.0, "low": 100.2, "close": 100.7},
            {"open": 100.7, "high": 101.5, "low": 100.6, "close": 101.2},
            {"open": 101.2, "high": 102.0, "low": 101.0, "close": 101.8},
        ])
        return {"symbol": "BTCUSDT", "1h": hourly, "15m": fifteen, "5m": five}

    def test_generates_long_plan_only_after_regime_and_quality_checks(self):
        plan = self.strategy.analyze(self.market_frames(), market="futures")
        self.assertTrue(plan["success"], plan)
        self.assertEqual(plan["direction"], "LONG")
        self.assertEqual(plan["market_regime"], "BULLISH")
        self.assertLess(plan["stop_loss"], plan["entry"])
        self.assertGreater(plan["take_profit"], plan["entry"])
        self.assertGreaterEqual(plan["net_reward_risk"], 1.5)

    def test_spot_is_blocked_in_bearish_regime(self):
        data = self.market_frames()
        hourly = data["1h"].copy()
        hourly["close"] = 90.0
        hourly["EMA_50"] = [95.0 - i * 0.2 for i in range(len(hourly))]
        hourly["PLUS_DI"], hourly["MINUS_DI"] = 10.0, 30.0
        data["1h"] = hourly
        plan = self.strategy.analyze(data, market="spot")
        self.assertFalse(plan["success"])
        self.assertEqual(plan["market_regime"], "BEARISH")

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
