import tempfile
import unittest
from pathlib import Path

from core.journal import TradeJournal


class ClosedTradeArchiveTests(unittest.TestCase):
    def test_closed_snapshot_is_archived_without_open_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = TradeJournal(Path(tmp) / "journal.db")
            record = {
                "trade_id": "futures_manual_close_1",
                "domain": "futures",
                "symbol": "BTCUSDT",
                "direction": "LONG",
                "entry_price": "65000",
                "close_price": "65200",
                "stop_loss": "64500",
                "take_profit": "66000",
                "opened_at_ms": 1000,
                "closed_at_ms": 2000,
                "risk_amount": "25",
                "setup_key": "manual-test",
                "context": {"timeframe": "5m"},
            }

            self.assertTrue(journal.record_closed_snapshot(record, 7.5, "MANUAL"))
            trades = journal.closed_trades()

            self.assertEqual(len(trades), 1)
            self.assertEqual(trades[0]["trade_id"], "futures_manual_close_1")
            self.assertEqual(trades[0]["status"], "CLOSED")
            self.assertEqual(trades[0]["entry"], 65000)
            self.assertEqual(trades[0]["exit_price"], 65200)
            self.assertEqual(trades[0]["net_pnl"], 7.5)
            self.assertEqual(trades[0]["close_reason"], "MANUAL")
            self.assertEqual(trades[0]["context"]["timeframe"], "5m")

    def test_closed_snapshot_upgrades_existing_open_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = TradeJournal(Path(tmp) / "journal.db")
            journal.record_open(
                "spot_trade_2", "spot", "ETHUSDT", "LONG",
                "setup-2", 0.8, 3000, 2900, 3300, 20,
                {"timeframe": "15m"},
            )
            record = {
                "trade_id": "spot_trade_2",
                "domain": "spot",
                "symbol": "ETHUSDT",
                "direction": "LONG",
                "entry_price": 3000,
                "close_price": 3100,
                "stop_loss": 2900,
                "take_profit": 3300,
                "opened_at_ms": 1000,
                "closed_at_ms": 2000,
                "risk_amount": 20,
                "context": {"timeframe": "15m"},
            }

            journal.record_closed_snapshot(record, 5, "TAKE_PROFIT")
            trades = journal.closed_trades()

            self.assertEqual(len(trades), 1)
            self.assertEqual(trades[0]["status"], "CLOSED")
            self.assertEqual(trades[0]["net_pnl"], 5)
            self.assertEqual(trades[0]["close_reason"], "TAKE_PROFIT")


if __name__ == "__main__":
    unittest.main()
