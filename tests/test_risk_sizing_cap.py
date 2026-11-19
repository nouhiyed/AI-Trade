import os
import tempfile
import unittest

from core.risk_manager import RiskManager


class TestRiskSizingCap(unittest.TestCase):
    def setUp(self):
        self.original_cwd = os.getcwd()
        self.temp_dir = tempfile.TemporaryDirectory()
        os.chdir(self.temp_dir.name)
        self.risk = RiskManager(initial_balance=1000)

    def tearDown(self):
        os.chdir(self.original_cwd)
        self.temp_dir.cleanup()

    def test_oversized_futures_position_is_capped_not_rejected(self):
        result = self.risk.reserve_trade(
            domain="futures", symbol="BTCUSDT", direction="LONG",
            entry=100, stop_loss=99.9, risk_pct=0.5, leverage=5)
        self.assertTrue(result["approved"], result)
        self.assertTrue(result["sizing_capped"])
        self.assertAlmostEqual(result["margin"], 250.0)
        self.assertAlmostEqual(result["requested_risk"], 5.0)
        self.assertAlmostEqual(result["risk"], 1.25)
        self.assertAlmostEqual(result["notional"], 1250.0)

    def test_spot_position_uses_same_wallet_cap_at_one_x(self):
        result = self.risk.reserve_trade(
            domain="spot", symbol="ETHUSDT", direction="LONG",
            entry=100, stop_loss=99.9, risk_pct=0.5, leverage=1)
        self.assertTrue(result["approved"], result)
        self.assertTrue(result["sizing_capped"])
        self.assertAlmostEqual(result["margin"], 250.0)
        self.assertAlmostEqual(result["notional"], 250.0)
        self.assertAlmostEqual(result["risk"], 0.25)


if __name__ == "__main__":
    unittest.main()
