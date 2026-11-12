import unittest

import pandas as pd

from scripts.backtest import _bar_hit, _fill_entry, _fill_exit


class TestHistoricalBacktestExecution(unittest.TestCase):
    def test_taker_slippage_is_applied_against_the_position(self):
        slip = 0.0005
        self.assertAlmostEqual(_fill_entry(100.0, "LONG", slip), 100.05)
        self.assertAlmostEqual(_fill_entry(100.0, "SHORT", slip), 99.95)
        self.assertAlmostEqual(_fill_exit(100.0, "LONG", slip), 99.95)
        self.assertAlmostEqual(_fill_exit(100.0, "SHORT", slip), 100.05)

    def test_stop_gap_fills_at_the_open_not_the_better_stop_price(self):
        bar = pd.Series({"open": 97.0, "high": 99.0, "low": 96.0})
        hit, price = _bar_hit(bar, "LONG", 98.0, True)
        self.assertTrue(hit)
        self.assertEqual(price, 97.0)

    def test_target_gap_uses_the_favorable_open(self):
        bar = pd.Series({"open": 103.0, "high": 104.0, "low": 102.0})
        hit, price = _bar_hit(bar, "LONG", 102.0, False)
        self.assertTrue(hit)
        self.assertEqual(price, 103.0)

    def test_intrabar_stop_and_target_are_both_detectable_for_stop_first_rule(self):
        bar = pd.Series({"open": 100.0, "high": 103.0, "low": 97.0})
        stop_hit, _ = _bar_hit(bar, "LONG", 98.0, True)
        target_hit, _ = _bar_hit(bar, "LONG", 102.0, False)
        self.assertTrue(stop_hit)
        self.assertTrue(target_hit)


if __name__ == "__main__":
    unittest.main()
