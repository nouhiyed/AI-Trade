import os
import tempfile
import unittest

from core.risk_manager import RiskManager


class TestRiskManager(unittest.TestCase):
    def setUp(self):
        self.original_cwd = os.getcwd()
        self.temp_dir = tempfile.TemporaryDirectory()
        os.chdir(self.temp_dir.name)
        self.risk = RiskManager(initial_balance=1000)

    def tearDown(self):
        os.chdir(self.original_cwd)
        self.temp_dir.cleanup()

    def reserve(self):
        return self.risk.reserve_trade(
            domain="futures",
            symbol="BTCUSDT",
            direction="LONG",
            entry=100000,
            stop_loss=99000,
            risk_pct=0.5,
            leverage=5,
        )

    def test_reserve_trade(self):
        result = self.reserve()
        self.assertTrue(result["approved"])
        self.assertAlmostEqual(result["risk"], 5.0)
        self.assertEqual(len(self.risk.reservations), 1)

    def test_close_and_persist(self):
        trade = self.reserve()
        self.assertTrue(trade["approved"])

        result = self.risk.close_trade(
            trade["trade_id"], -5
        )
        self.assertTrue(result["success"])
        self.assertAlmostEqual(self.risk.balance, 995)
        self.assertAlmostEqual(self.risk.daily_loss, 5)
        self.assertEqual(len(self.risk.reservations), 0)

        restored = RiskManager(initial_balance=1000)
        self.assertAlmostEqual(restored.balance, 995)
        self.assertAlmostEqual(restored.daily_loss, 5)
        self.assertEqual(len(restored.reservations), 0)

    def test_invalid_trade_rejected(self):
        result = self.risk.reserve_trade(
            domain="futures",
            symbol="BTCUSDT",
            direction="LONG",
            entry=100,
            stop_loss=110,
        )
        self.assertFalse(result["approved"])

    def test_futures_leverage_hard_cap(self):
        result = self.risk.reserve_trade(
            domain="futures", symbol="BTCUSDT", direction="LONG",
            entry=100, stop_loss=99, risk_pct=0.5, leverage=6)
        self.assertFalse(result["approved"])
        self.assertIn("5x", result["reason"])

    def test_spot_is_unleveraged(self):
        result = self.risk.reserve_trade(
            domain="spot", symbol="ETHUSDT", direction="LONG",
            entry=100, stop_loss=99, risk_pct=0.5, leverage=2)
        self.assertFalse(result["approved"])
        self.assertIn("1x", result["reason"])

    def test_unknown_trade_close(self):
        result = self.risk.close_trade("missing_trade", 10)
        self.assertFalse(result["success"])


if __name__ == "__main__":
    unittest.main()
