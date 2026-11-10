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

    def test_chart_submission_routes_approved_trade_to_executor(self):
        self.system.analyze_live = lambda symbol, preferred_timeframe=None: {
            "signals": {
                "futures": {
                    "symbol": symbol,
                    "direction": "LONG",
                    "confidence": 82,
                    "trade_plan": {
                        "success": True, "direction": "LONG",
                        "entry": 100, "stop_loss": 99,
                        "take_profit": 102, "atr": 0.5,
                    },
                }
            }
        }
        calls = []
        def execute_chart_trade(symbol, direction, signal_override=None):
            calls.append((symbol, direction, signal_override))
            return {"approved": True, "position_id": "demo-test"}
        self.system.request_demo_futures_trade = execute_chart_trade
        result = self.system.submit_chart_signal("futures", "BTCUSDT", "5m", 100, 102, 99)
        self.assertTrue(result["success"], result)
        self.assertTrue(result["opened"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0:2], ("BTCUSDT", "LONG"))
        self.assertIsNotNone(calls[0][2])
        self.assertEqual(calls[0][2]["trade_plan"]["entry"], 100)
        self.assertEqual(calls[0][2]["trade_plan"]["take_profit"], 102)
        self.assertEqual(calls[0][2]["trade_plan"]["stop_loss"], 99)
        self.assertEqual(result["signal"]["chart_timeframe"], "5m")
        self.assertEqual(result["trade_plan"]["entry"], 100)
        self.assertEqual(result["trade_plan"]["take_profit"], 102)
        self.assertEqual(result["trade_plan"]["stop_loss"], 99)

    def test_chart_submission_does_not_execute_rejected_signal(self):
        self.system.analyze_live = lambda symbol, preferred_timeframe=None: {
            "signals": {"futures": {
                "symbol": symbol, "direction": "WAIT", "confidence": 12,
                "reason": "No directional edge",
            }}
        }
        self.system.request_demo_futures_trade = lambda *a, **k: self.fail(
            "Rejected chart signal must not reach execution")
        result = self.system.submit_chart_signal("futures", "BTCUSDT", "5m", 100, 102, 99)
        self.assertTrue(result["success"])
        self.assertFalse(result["opened"])
        self.assertEqual(result["decision_status"], "REJECTED")
        self.assertTrue(result.get("decision_reason"))
        self.assertIn("No directional edge", result["decision_reason"])

    def test_chart_submission_rejects_invalid_proposed_level_order(self):
        self.system.analyze_live = lambda symbol, preferred_timeframe=None: {
            "signals": {"futures": {
                "symbol": symbol, "direction": "LONG", "confidence": 80,
                "trade_plan": {
                    "success": True, "direction": "LONG",
                    "entry": 100, "stop_loss": 99, "take_profit": 102,
                },
            }}
        }
        self.system.request_demo_futures_trade = lambda *a, **k: self.fail(
            "Invalid proposed levels must not reach execution")
        result = self.system.submit_chart_signal(
            "futures", "BTCUSDT", "1m", 100, 98, 99)
        self.assertEqual(result["decision_status"], "REJECTED")
        self.assertIn("Stop Loss", result["decision_reason"])

    def test_spot_and_alpha_accept_one_minute_chart_timeframe(self):
        self.assertIn("1m", self.system.required_timeframes["spot"])
        self.assertIn("1m", self.system.required_timeframes["alpha"])

    def test_market_data_failure_before_order_releases_reservation(self):
        self.system.last_signals["futures"] = {
            "symbol": "BTCUSDT", "direction": "LONG", "confidence": 80,
            "trade_plan": {
                "success": True, "direction": "LONG", "entry": 100,
                "stop_loss": 99, "take_profit": 102, "atr": 0.5,
            },
        }
        self.system._demo_market_price = lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("Binance quote unavailable"))
        result = self.system.request_demo_futures_trade("BTCUSDT", "LONG")
        self.assertFalse(result["approved"])
        self.assertFalse(result["execution_submitted"])
        self.assertEqual(self.system.risk.get_status()["active_reservations"], 0)
        self.assertEqual(self.system.demo_positions, {})

    def test_futures_leverage_is_confidence_and_volatility_aware(self):
        plan = {"entry": 100, "atr": 0.5}
        self.assertEqual(
            self.system.select_futures_leverage({"confidence": 85}, plan), 5)
        self.assertEqual(
            self.system.select_futures_leverage({"confidence": 72}, plan), 3)
        self.assertEqual(
            self.system.select_futures_leverage({"confidence": 72},
                                                {"entry": 100, "atr": 2.0}), 2)
        self.assertEqual(
            self.system.select_futures_leverage({"confidence": 54}, plan), 1)

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
