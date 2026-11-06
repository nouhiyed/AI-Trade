import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core.paper_trading_engine import PaperTradingEngine
from core.coordinator import TradingCoordinator


class FakeFeed:
    def __init__(self, prices):
        self.prices = prices

    def fetch_book_ticker(self, market, symbol):
        bid, ask = self.prices[symbol]
        return {"bid": bid, "ask": ask}


class FakeAgent:
    def record_trade(self, trade):
        pass


class TestPaperMonitor(unittest.TestCase):

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.paper = PaperTradingEngine(
            initial_balance=10000,
            state_path=str(Path(self.tmp.name) / "paper.json"),
        )
        self.bot = TradingCoordinator.__new__(TradingCoordinator)
        self.bot.paper = self.paper
        self.bot.agents = {
            "futures": FakeAgent(),
            "spot": FakeAgent(),
            "alpha": FakeAgent(),
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_auto_closes_stop_loss_and_take_profit(self):
        self.paper.open_position(
            "futures", "BTCUSDT", "LONG", 100, 1,
            stop_loss=95, take_profit=110,
        )
        self.paper.open_position(
            "futures", "ETHUSDT", "LONG", 100, 1,
            stop_loss=95, take_profit=108,
        )
        self.paper.open_position(
            "futures", "SOLUSDT", "SHORT", 100, 1,
            stop_loss=106, take_profit=90,
        )

        self.bot.paper_price_feed = FakeFeed({
            "BTCUSDT": (94, 94.1),
            "ETHUSDT": (109, 109.1),
            "SOLUSDT": (105.9, 106.1),
        })

        result = self.bot.monitor_paper_positions()
        closes = [
            t for t in self.paper.get_trade_history()
            if t["action"] == "CLOSE"
        ]

        self.assertEqual(result["checked"], 3)
        self.assertEqual(len(closes), 3)
        self.assertEqual(self.paper.get_status()["open_count"], 0)
        self.assertEqual(
            {t["reason"] for t in closes},
            {"STOP_LOSS", "TAKE_PROFIT"},
        )

    def test_keeps_position_when_levels_not_reached(self):
        self.paper.open_position(
            "futures", "BTCUSDT", "LONG", 100, 1,
            stop_loss=95, take_profit=110,
        )

        self.bot.paper_price_feed = FakeFeed({
            "BTCUSDT": (99.9, 100.1),
        })

        result = self.bot.monitor_paper_positions()

        self.assertEqual(result["events"], [])
        self.assertEqual(self.paper.get_status()["open_count"], 1)


    def test_failed_auto_close_is_not_reported_as_success(self):
        self.paper.open_position(
            "futures", "BTCUSDT", "LONG", 100, 1,
            stop_loss=95, take_profit=110,
        )

        self.bot.paper_price_feed = FakeFeed({
            "BTCUSDT": (94, 94.1),
        })

        self.bot.close_paper_trade = lambda **kwargs: {
            "success": False,
            "reason": "Position already closed",
        }

        result = self.bot.monitor_paper_positions()

        self.assertEqual(len(result["events"]), 1)
        self.assertTrue(result["events"][0]["close_failed"])
        self.assertNotIn("reason", result["events"][0])
        self.assertEqual(self.paper.get_status()["open_count"], 1)


    def test_manual_market_close_uses_correct_side_and_only_target_position(self):
        long_result = self.paper.open_position(
            "futures", "BTCUSDT", "LONG", 100, 1
        )
        short_result = self.paper.open_position(
            "futures", "ETHUSDT", "SHORT", 100, 1
        )
        untouched_result = self.paper.open_position(
            "futures", "SOLUSDT", "LONG", 100, 1
        )

        long_id = long_result["position"]["id"]
        short_id = short_result["position"]["id"]
        untouched_id = untouched_result["position"]["id"]

        self.bot.paper_price_feed = FakeFeed({
            "BTCUSDT": (99, 100),
            "ETHUSDT": (100, 101),
            "SOLUSDT": (98, 99),
        })

        # LONG must close using bid.
        closed_long = self.bot.close_paper_position_at_market(long_id)

        self.assertTrue(closed_long["success"])
        self.assertEqual(closed_long["exit_quote"]["selected_price"], 99)
        self.assertEqual(closed_long["exit_quote"]["bid"], 99)
        self.assertEqual(closed_long["trade"]["reason"], "MANUAL")
        self.assertEqual(closed_long["trade"]["position_id"], long_id)

        remaining = self.paper.get_status()["open_positions"]
        remaining_ids = {item["id"] for item in remaining}

        self.assertNotIn(long_id, remaining_ids)
        self.assertIn(short_id, remaining_ids)
        self.assertIn(untouched_id, remaining_ids)

        # SHORT must close using ask.
        closed_short = self.bot.close_paper_position_at_market(short_id)

        self.assertTrue(closed_short["success"])
        self.assertEqual(closed_short["exit_quote"]["selected_price"], 101)
        self.assertEqual(closed_short["trade"]["reason"], "MANUAL")
        self.assertEqual(closed_short["trade"]["position_id"], short_id)

        # A second close request must fail.
        repeated = self.bot.close_paper_position_at_market(long_id)
        self.assertFalse(repeated["success"])

        remaining = self.paper.get_status()["open_positions"]
        self.assertEqual(
            [item["id"] for item in remaining],
            [untouched_id],
        )

        closes = [
            trade for trade in self.paper.get_trade_history()
            if trade["action"] == "CLOSE"
        ]
        self.assertEqual(len(closes), 2)
        self.assertEqual(
            {trade["reason"] for trade in closes},
            {"MANUAL"},
        )


if __name__ == "__main__":
    unittest.main()
