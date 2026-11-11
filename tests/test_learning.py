import tempfile
import unittest
from pathlib import Path

from core.journal import TradeJournal
from core.learning import LearningEngine, setup_key


class TestLearningEngine(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.journal = TradeJournal(Path(self.temp.name) / "journal.db")
        self.learning = LearningEngine(self.journal, min_samples=20)

    def tearDown(self):
        self.temp.cleanup()

    def add_closed(self, count, pnl, setup="momentum|SHORT|c80|rr2+"):
        for i in range(count):
            trade_id = f"{setup}-{i}"
            self.journal.record_open(
                trade_id, "futures", "BTCUSDT", "SHORT", setup, 80,
                100, 101, 98, risk_amount=1,
                context={"features": {"rsi_oversold": True, "adx_trending": False}},
            )
            self.journal.record_close(trade_id, pnl, exit_price=99 if pnl > 0 else 102,
                                      reason="TAKE_PROFIT" if pnl > 0 else "STOP_LOSS")

    def test_setup_is_not_disabled_before_20_closed_trades(self):
        self.add_closed(19, -1)
        self.assertEqual(self.learning.evaluate(), [])
        self.assertEqual(self.journal.disabled_setups(), {})

    def test_losing_setup_is_flagged_after_20_closed_trades(self):
        self.add_closed(20, -1)
        disabled = self.learning.evaluate()
        self.assertEqual(len(disabled), 1)
        self.assertIn("20 trades", disabled[0]["reason"])
        self.assertFalse(self.learning.allows("momentum|SHORT|c80|rr2+"))

    def test_report_ranks_features_and_marks_sample_maturity(self):
        self.add_closed(20, 1)
        report = self.learning.report()
        self.assertEqual(report["min_samples"], 20)
        self.assertEqual(report["closed_trades"], 20)
        features = {item["feature"]: item for item in report["features"]}
        self.assertTrue(features["rsi_oversold:on"]["mature"])
        self.assertEqual(features["rsi_oversold"]["trades"], 20)

    def test_setup_key_separates_entry_strategy(self):
        a = setup_key("SHORT", 80, 2.1, "futures", "liquidity_reversal")
        b = setup_key("SHORT", 80, 2.1, "futures", "structure_breakout")
        self.assertNotEqual(a, b)


if __name__ == "__main__":
    unittest.main()
