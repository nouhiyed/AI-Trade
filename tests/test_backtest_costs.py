import unittest

from core.backtest_costs import BacktestCostModel, apply_funding


class BacktestCostTests(unittest.TestCase):
    def test_costs_increase_with_volatility_and_fall_with_liquidity(self):
        model = BacktestCostModel("spot")
        quiet = model.components({"close": 100, "ATR": 0.1, "quote_volume": 10_000_000})
        volatile = model.components({"close": 100, "ATR": 2.0, "quote_volume": 10_000_000})
        illiquid = model.components({"close": 100, "ATR": 0.1, "quote_volume": 10_000})
        self.assertGreater(volatile["total_adverse_rate"], quiet["total_adverse_rate"])
        self.assertGreater(illiquid["total_adverse_rate"], quiet["total_adverse_rate"])
        self.assertLessEqual(volatile["total_adverse_rate"], 0.0037)

    def test_funding_sign_depends_on_side_and_rate(self):
        long = {"market": "futures", "direction": "LONG", "remaining_quantity": 2}
        short = {"market": "futures", "direction": "SHORT", "remaining_quantity": 2}
        self.assertAlmostEqual(apply_funding(long, 0.001, 100), -0.2)
        self.assertAlmostEqual(apply_funding(short, 0.001, 100), 0.2)
        self.assertAlmostEqual(apply_funding(long, -0.001, 100), 0.2)

    def test_spot_has_no_funding(self):
        spot = {"market": "spot", "direction": "LONG", "remaining_quantity": 2}
        self.assertEqual(apply_funding(spot, 0.01, 100), 0.0)


if __name__ == "__main__":
    unittest.main()
