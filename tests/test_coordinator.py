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


    def test_futures_paper_rejects_missing_trade_plan(self):
        self.system.last_signals["futures"] = {
            "symbol": "BTCUSDT",
            "direction": "LONG",
        }

        result = self.system.request_paper_trade(
            domain="futures",
            symbol="BTCUSDT",
            direction="LONG",
            entry=100,
            quantity=0.1,
            stop_loss=95,
            take_profit=110,
        )

        self.assertFalse(result["approved"])
        self.assertEqual(
            result["reason"],
            "No approved Futures trade plan",
        )

    def test_futures_paper_rejects_invalid_plan_levels(self):
        self.system.last_signals["futures"] = {
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "trade_plan": {
                "success": True,
                "direction": "LONG",
                "entry": 100,
                "stop_loss": 101,
                "take_profit": 110,
            },
        }

        result = self.system.request_paper_trade(
            domain="futures",
            symbol="BTCUSDT",
            direction="LONG",
            entry=100,
            quantity=0.1,
        )

        self.assertFalse(result["approved"])
        self.assertEqual(
            result["reason"],
            "Futures plan levels or reward/risk rejected",
        )

    def test_futures_paper_uses_approved_plan_levels(self):
        plan = {
            "success": True,
            "direction": "LONG",
            "entry": 100,
            "stop_loss": 95,
            "take_profit": 110,
        }
        self.system.last_signals["futures"] = {
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "trade_plan": plan,
        }

        captured = {}

        def fake_open_position(**kwargs):
            captured.update(kwargs)
            return {"success": True, "position_id": "paper-test"}

        self.system.paper.open_position = fake_open_position

        result = self.system.request_paper_trade(
            domain="futures",
            symbol="BTCUSDT",
            direction="LONG",
            entry=999,
            quantity=0.1,
            stop_loss=998,
            take_profit=1000,
        )

        self.assertTrue(result["approved"])
        self.assertEqual(captured["price"], 100)
        self.assertEqual(captured["stop_loss"], 95)
        self.assertEqual(captured["take_profit"], 110)


if __name__ == "__main__":
    unittest.main()
