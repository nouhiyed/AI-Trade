import unittest

import pandas as pd

from core.adaptive_trend import AdaptiveTrendStrategy


class AdaptiveTrendTests(unittest.TestCase):
    def setUp(self):
        self.strategy = AdaptiveTrendStrategy()

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
