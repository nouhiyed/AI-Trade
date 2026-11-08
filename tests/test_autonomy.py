import os
import tempfile
import time
import unittest

import pandas as pd

from core import performance
from core.autopilot import Autopilot
from core.chart_image import render_trade_chart
from core.coordinator import TradingCoordinator
from core.learning import setup_key
from core.market_context import MarketContext, classify_headline, parse_rss
from core.notifier import Notifier


class Feed:
    def __init__(self):
        self.prices = {}
        self.candles = []          # list of (minutes_ago, high, low)

    def fetch_book_ticker(self, market, symbol):
        p = self.prices.get(symbol, 100.0)
        return {"bid": p - 0.01, "ask": p + 0.01, "mid_price": p}

    def fetch_candles(self, market, symbol, interval="1m", limit=500, closed_only=True):
        now = pd.Timestamp.now(tz="UTC").floor("min")
        rows = []
        for ago, high, low in self.candles:
            t = now - pd.Timedelta(minutes=ago)
            rows.append({"open_time": t, "close_time": t + pd.Timedelta(seconds=59),
                         "open": 100.0, "high": high, "low": low, "close": 100.0})
        return pd.DataFrame(rows)


def plan(symbol, direction="LONG", entry=100, stop=99, target=102):
    return {"symbol": symbol, "direction": direction, "confidence": 80,
            "trade_plan": {"success": True, "direction": direction, "entry": entry,
                           "stop_loss": stop, "take_profit": target, "reward_risk": 2.0}}


class Base(unittest.TestCase):
    def setUp(self):
        self.cwd = os.getcwd()
        self.tmp = tempfile.TemporaryDirectory()
        os.chdir(self.tmp.name)
        self.c = TradingCoordinator(initial_balance=10000)
        self.feed = Feed()
        self.c.market_feed = self.feed

    def tearDown(self):
        self.c.demo_database.connection.close()
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def open(self, symbol="BTCUSDT", direction="LONG", **kw):
        self.c.last_signals["futures"] = plan(symbol, direction, **kw)
        return self.c.request_demo_futures_trade(symbol, direction, 0.25, 2)


class TestJournalAndConcurrency(Base):
    def test_two_symbols_then_same_symbol_rejected(self):
        a = self.open("BTCUSDT")
        b = self.open("ETHUSDT")
        self.assertTrue(a["approved"] and b["approved"], (a, b))
        dup = self.open("BTCUSDT")
        self.assertFalse(dup["approved"])
        self.assertEqual(len(self.c.journal.recent()), 2)

    def test_close_updates_journal_with_net_pnl_and_r(self):
        a = self.open("BTCUSDT")
        self.c.close_demo_position(a["position_id"])
        row = self.c.journal.closed_trades()[0]
        self.assertEqual(row["close_reason"], "MANUAL")
        self.assertLess(row["net_pnl"], 0)            # fees + slippage
        self.assertIsNotNone(row["r_multiple"])
        self.assertAlmostEqual(
            self.c.risk.balance,
            float(self.c.demo_execution.get_account_summary("primary")["wallet_balance"]),
            places=6)

    def test_two_open_trades_settle_independently(self):
        a = self.open("BTCUSDT")
        b = self.open("ETHUSDT")
        self.c.close_demo_position(a["position_id"])
        self.assertEqual(self.c.risk.get_status()["active_reservations"], 1)
        self.c.close_demo_position(b["position_id"])
        self.assertEqual(self.c.risk.get_status()["active_reservations"], 0)
        wallet = float(self.c.demo_execution.get_account_summary("primary")["wallet_balance"])
        self.assertAlmostEqual(self.c.risk.balance, wallet, places=6)
        self.assertEqual(len(self.c.journal.closed_trades()), 2)


class TestOutageCatchUp(Base):
    def test_stop_touched_during_outage_is_closed_at_stop(self):
        a = self.open("BTCUSDT")
        rec = self.c.demo_positions[a["position_id"]]
        rec["last_checked_ms"] = int((time.time() - 600) * 1000)
        # a candle 5 minutes ago dipped below the stop; price is back at 100 now
        self.feed.candles = [(8, 100.5, 99.5), (5, 100.4, 98.7), (3, 100.2, 99.6)]
        events = self.c.monitor_demo_positions()["events"]
        self.assertEqual(events[0]["reason"], "STOP_LOSS")
        self.assertEqual(self.c.demo_positions[a["position_id"]]["status"], "DEMO_CLOSED")

    def test_target_touched_during_outage(self):
        a = self.open("BTCUSDT")
        self.c.demo_positions[a["position_id"]]["last_checked_ms"] = int((time.time() - 600) * 1000)
        self.feed.candles = [(4, 102.5, 100.1)]
        events = self.c.monitor_demo_positions()["events"]
        self.assertEqual(events[0]["reason"], "TAKE_PROFIT")

    def test_candle_before_last_check_is_ignored(self):
        a = self.open("BTCUSDT")
        self.c.demo_positions[a["position_id"]]["last_checked_ms"] = int((time.time() - 120) * 1000)
        self.feed.candles = [(10, 105.0, 90.0)]       # older than the last check
        self.assertEqual(self.c.monitor_demo_positions()["events"], [])


class TestAutopilot(Base):
    def _scan(self, symbols):
        def scan_futures(limit=12, **_):
            opps = []
            for s, conf in symbols:
                p = plan(s)
                opps.append({"symbol": s, "direction": "LONG", "confidence": conf,
                             "trade_plan": p["trade_plan"], "signal": p})
            return {"success": True, "scanned": len(opps), "actionable": len(opps),
                    "opportunities": opps}
        self.c.scan_futures = scan_futures

    def test_off_by_default(self):
        ap = Autopilot(self.c, config_path="config/ap.json")
        self.assertEqual(ap.tick()["opened"], [])

    def test_opens_respecting_confidence_and_limits(self):
        self._scan([("BTCUSDT", 80), ("ETHUSDT", 40), ("SOLUSDT", 75)])
        ap = Autopilot(self.c, config_path="config/ap.json")
        ap.update({"enabled": True, "max_concurrent": 2, "min_confidence": 60})
        out = ap.tick()
        self.assertEqual([o["symbol"] for o in out["opened"]], ["BTCUSDT", "SOLUSDT"])
        self.assertTrue(any(s.get("symbol") == "ETHUSDT" for s in out["skipped"]))
        again = ap.tick()
        self.assertEqual(again["opened"], [])
        self.assertEqual(len(self.c.journal.recent()), 2)

    def test_learning_disabled_setup_is_skipped(self):
        self._scan([("BTCUSDT", 80)])
        key = setup_key("LONG", 80, 2.0)
        self.c.journal.set_setup_disabled(key, True, "test")
        ap = Autopilot(self.c, config_path="config/ap.json")
        ap.update({"enabled": True})
        out = ap.tick()
        self.assertEqual(out["opened"], [])
        self.assertIn("disabled by learning", out["skipped"][0]["reason"])

    def test_context_veto_blocks_trade(self):
        class Ctx:
            def assess(self, symbol, direction):
                return {"score": -3, "flags": [], "veto": "Severe adverse news", "details": {}}
        self._scan([("BTCUSDT", 90)])
        ap = Autopilot(self.c, context=Ctx(), config_path="config/ap.json")
        ap.update({"enabled": True})
        out = ap.tick()
        self.assertEqual(out["opened"], [])
        self.assertIn("Context veto", out["skipped"][0]["reason"])

    def test_config_is_clamped(self):
        ap = Autopilot(self.c, config_path="config/ap.json")
        ap.update({"leverage": 500, "max_concurrent": 99, "risk_pct": "x"})
        self.assertEqual(ap.config["leverage"], 5)
        self.assertEqual(ap.config["max_concurrent"], 5)
        self.assertEqual(ap.config["risk_pct"], 0.5)


class TestLearningAndPerformance(Base):
    def _add(self, key, pnl, r, i):
        self.c.journal.record_open(f"t{key}{i}", "futures", "BTCUSDT", "LONG", key,
                                   70, 100, 99, 102, 10)
        self.c.journal.record_close(f"t{key}{i}", pnl, 99, "STOP_LOSS")

    def test_metrics(self):
        trades = [{"net_pnl": 10, "r_multiple": 1, "domain": "futures", "setup_key": "a",
                   "close_reason": "TAKE_PROFIT", "status": "CLOSED"},
                  {"net_pnl": -5, "r_multiple": -.5, "domain": "futures", "setup_key": "a",
                   "close_reason": "STOP_LOSS", "status": "CLOSED"},
                  {"net_pnl": -5, "r_multiple": -.5, "domain": "futures", "setup_key": "a",
                   "close_reason": "STOP_LOSS", "status": "CLOSED"}]
        o = performance.compute(trades)["overall"]
        self.assertEqual(o["trades"], 3)
        self.assertAlmostEqual(o["win_rate"], 33.33, places=1)
        self.assertEqual(o["net_pnl"], 0)
        self.assertEqual(o["max_drawdown"], 10)
        self.assertEqual(o["profit_factor"], 1.0)

    def test_no_change_before_enough_samples_then_disables_loser(self):
        key = "LONG|c80|rr2+"
        for i in range(29):
            self._add(key, -10, -1, i)
        self.assertEqual(self.c.learning.evaluate(), [])
        self.assertTrue(self.c.learning.allows(key))
        self._add(key, -10, -1, 29)
        self.assertEqual(len(self.c.learning.evaluate()), 1)
        self.assertFalse(self.c.learning.allows(key))
        rep = self.c.learning.report()
        self.assertTrue(rep["setups"][0]["disabled"])

    def test_profitable_setup_stays_enabled(self):
        key = "SHORT|c65|rr2+"
        for i in range(40):
            self._add(key, 10 if i % 2 else -5, 1 if i % 2 else -.5, i)
        self.assertEqual(self.c.learning.evaluate(), [])


class TestContext(unittest.TestCase):
    def test_headlines(self):
        self.assertEqual(classify_headline("Exchange hacked, funds drained"), -2)
        self.assertEqual(classify_headline("Bitcoin ETF approved"), 1)
        self.assertEqual(classify_headline("Market quiet today"), 0)

    def test_rss_parse(self):
        xml = "<rss><channel><item><title>Solana hack drains $50M</title></item></channel></rss>"
        self.assertEqual(parse_rss(xml)[0]["title"], "Solana hack drains $50M")
        self.assertEqual(parse_rss("not xml"), [])

    def test_assess_vetoes_on_severe_news_and_fails_soft(self):
        class Resp:
            def __init__(self, text="", data=None):
                self.text, self._d = text, data
            def raise_for_status(self): pass
            def json(self): return self._d

        class Sess:
            headers = {}
            def get(self, url, params=None, timeout=None):
                if "rss" in url or "feed" in url:
                    return Resp("<rss><channel><item><title>Solana network exploit drained</title>"
                                "</item></channel></rss>")
                raise RuntimeError("down")        # all Binance calls fail

        ctx = MarketContext(session=Sess(), feeds=("https://x/rss",))
        out = ctx.assess("SOLUSDT", "LONG")
        self.assertIsNotNone(out["veto"])
        calm = ctx.assess("SOLUSDT", "SHORT")
        self.assertIsNone(calm["veto"])           # bad news is fine for a short

    def test_whale_flow_split(self):
        class Sess:
            headers = {}
            def get(self, *a, **k):
                class R:
                    def raise_for_status(self): pass
                    def json(self):
                        return [{"p": "100", "q": "2000", "m": False},
                                {"p": "100", "q": "1500", "m": True},
                                {"p": "100", "q": "1", "m": False}]
                return R()
        flow = MarketContext(session=Sess()).whale_flow("BTCUSDT")
        self.assertEqual(flow["buy_usd"], 200000)
        self.assertEqual(flow["sell_usd"], 150000)
        self.assertEqual(flow["large_trades"], 2)


class TestOutputs(unittest.TestCase):
    def test_chart_png(self):
        candles = [{"open": 100 + i * .1, "high": 101 + i * .1, "low": 99 + i * .1,
                    "close": 100.5 + i * .1} for i in range(40)]
        png = render_trade_chart(candles, "LONG", 102, 100, 106, "BTCUSDT")
        self.assertTrue(png.startswith(b"\x89PNG"))

    def test_notifier_disabled_without_keys(self):
        n = Notifier(token="", chat_id="")
        self.assertFalse(n.enabled)
        self.assertFalse(n.send_message("x"))


if __name__ == "__main__":
    unittest.main()
