import os
import tempfile
import unittest

from core.coordinator import TradingCoordinator


class Feed:
    def __init__(self):
        self.price = 100.0

    def fetch_book_ticker(self, market, symbol):
        return {"bid": self.price - 0.01, "ask": self.price + 0.01,
                "mid_price": self.price}


class TestDemoRiskRelease(unittest.TestCase):
    def setUp(self):
        self.cwd = os.getcwd()
        self.tmp = tempfile.TemporaryDirectory()
        os.chdir(self.tmp.name)
        self.c = TradingCoordinator(initial_balance=1000)
        self.feed = Feed()
        self.c.market_feed = self.feed

    def tearDown(self):
        self.c.demo_database.connection.close()
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def _signal(self):
        self.c.last_signals["futures"] = {
            "symbol": "BTCUSDT", "direction": "LONG",
            "trade_plan": {"success": True, "direction": "LONG",
                           "entry": 100, "stop_loss": 99, "take_profit": 103, "atr": 0.5},
        }

    def test_repeated_trades_release_risk_and_match_ledger(self):
        for _ in range(6):
            self._signal()
            self.feed.price = 100.0
            opened = self.c.request_demo_futures_trade("BTCUSDT", "LONG", 0.5, 1)
            self.assertTrue(opened["approved"], opened)
            closed = self.c.close_demo_position(opened["position_id"])
            self.assertTrue(closed["success"], closed)
            self.assertEqual(self.c.risk.get_status()["active_reservations"], 0)
        wallet = float(self.c.demo_execution.get_account_summary("primary")["wallet_balance"])
        self.assertAlmostEqual(self.c.risk.balance, wallet, places=6)
        self.assertGreater(self.c.risk.daily_loss, 0)

    def test_stop_loss_monitor_releases_risk(self):
        self._signal()
        opened = self.c.request_demo_futures_trade("BTCUSDT", "LONG", 0.5, 1)
        self.assertTrue(opened["approved"])
        self.feed.price = 98.5
        events = self.c.monitor_demo_positions()["events"]
        self.assertEqual(events[0]["reason"], "STOP_LOSS")
        self.assertEqual(self.c.risk.get_status()["active_reservations"], 0)
        self.assertEqual(self.c.demo_positions[opened["position_id"]]["status"], "DEMO_CLOSED")


if __name__ == "__main__":
    unittest.main()
