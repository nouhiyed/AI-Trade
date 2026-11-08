import os
import tempfile
import unittest

from core.coordinator import TradingCoordinator


class TestTradingCoordinator(unittest.TestCase):
    def setUp(self):
        self.original_cwd = os.getcwd()
        self.temp_dir = tempfile.TemporaryDirectory()
        os.chdir(self.temp_dir.name)
        self.system = TradingCoordinator(initial_balance=1000)

    def tearDown(self):
        os.chdir(self.original_cwd)
        self.temp_dir.cleanup()

    def test_agents_loaded(self):
        self.assertEqual(
            set(self.system.agents),
            {"futures", "spot", "alpha"},
        )

    def test_trade_requires_signal(self):
        result = self.system.request_trade(
            domain="futures",
            symbol="BTCUSDT",
            direction="LONG",
            entry=100000,
            stop_loss=99000,
        )
        self.assertFalse(result["approved"])

    def test_matching_signal_allows_reservation(self):
        self.system.last_signals["futures"] = {
            "direction": "LONG",
            "symbol": "BTCUSDT",
        }

        trade = self.system.request_trade(
            domain="futures",
            symbol="BTCUSDT",
            direction="LONG",
            entry=100000,
            stop_loss=99000,
            risk_pct=0.5,
            leverage=5,
        )
        self.assertTrue(trade["approved"])

        closed = self.system.close_trade(
            trade["trade_id"], 10
        )
        self.assertTrue(closed["success"])
        self.assertAlmostEqual(self.system.risk.balance, 1010)

    def test_alpha_execution_remains_disabled(self):
        result = self.system.request_trade(
            domain="alpha",
            symbol="TOKEN",
            direction="LONG",
            entry=1,
            stop_loss=0.9,
        )
        self.assertFalse(result["approved"])
        self.assertEqual(
            result["reason"], "Alpha execution disabled"
        )


    def test_paper_is_gone_and_live_is_locked(self):
        self.assertFalse(hasattr(self.system, "paper"))
        self.assertEqual(self.system.mode, "DEMO")
        self.assertTrue(self.system.set_mode("DEMO")["success"])
        self.assertFalse(self.system.set_mode("LIVE")["success"])
        self.assertFalse(self.system.set_mode("PAPER")["success"])


if __name__ == "__main__":
    unittest.main()
