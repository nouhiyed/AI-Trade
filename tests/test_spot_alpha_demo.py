import os
import tempfile
import time
import unittest

import pandas as pd

from core.autopilot import Autopilot
from core.coordinator import TradingCoordinator


class Feed:
    def __init__(self):
        self.prices = {}
        self.candles = []

    def fetch_book_ticker(self, market, symbol):
        p = self.prices.get(symbol, 100.0)
        return {"bid": p - 0.01, "ask": p + 0.01, "mid_price": p}

    def _build(self, symbol, *a, **k):
        now = pd.Timestamp.now(tz="UTC").floor("min")
        rows = []
        for ago, high, low in self.candles:
            t = now - pd.Timedelta(minutes=ago)
            rows.append({"open_time": t, "close_time": t + pd.Timedelta(seconds=59),
                         "open": 100.0, "high": high, "low": low, "close": 100.0})
        return pd.DataFrame(rows)

    def fetch_candles(self, market, symbol, interval="1m", limit=500, closed_only=True):
        return self._build(symbol)


def signal(symbol, entry, stop, target, safety=None):
    out = {"symbol": symbol, "direction": "BUY", "confidence": 80,
           "trade_plan": {"success": True, "direction": "LONG", "entry": entry,
                          "stop_loss": stop, "take_profit": target, "reward_risk": 2.0}}
    if safety is not None:
        out["token_safety"] = {"status": safety}
    return out


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

    def wallet(self):
        return float(self.c.demo_execution.get_account_summary("primary")["wallet_balance"])


class TestSpot(Base):
    def open(self, symbol="ETHUSDT"):
        self.feed.prices[symbol] = 100.0
        self.c.last_signals["spot"] = signal(symbol, 100, 98, 104)
        return self.c.request_demo_spot_trade(symbol, "spot", 0.25)

    def test_open_close_settles_risk_and_ledger(self):
        r = self.open()
        self.assertTrue(r["approved"], r)
        self.assertEqual(r["domain"], "spot")
        self.assertEqual(self.c.risk.get_status()["active_reservations"], 1)
        closed = self.c.close_demo_position(r["position_id"])
        self.assertTrue(closed["success"], closed)
        self.assertEqual(self.c.risk.get_status()["active_reservations"], 0)
        self.assertAlmostEqual(self.c.risk.balance, self.wallet(), places=6)
        row = self.c.journal.closed_trades()[0]
        self.assertEqual(row["domain"], "spot")
        self.assertLess(row["net_pnl"], 0)            # fees + slippage on a flat price
        self.assertEqual(self.c.demo_positions[r["position_id"]]["status"], "DEMO_CLOSED")

    def test_stop_loss_and_take_profit_by_live_price(self):
        a = self.open("ETHUSDT")
        self.feed.prices["ETHUSDT"] = 97.5
        ev = self.c.monitor_demo_positions()["events"]
        self.assertEqual(ev[0]["reason"], "STOP_LOSS")
        b = self.open("SOLUSDT")
        self.feed.prices["SOLUSDT"] = 104.5
        ev = self.c.monitor_demo_positions()["events"]
        self.assertEqual(ev[0]["reason"], "TAKE_PROFIT")
        self.assertAlmostEqual(self.c.risk.balance, self.wallet(), places=6)

    def test_catch_up_after_outage(self):
        r = self.open()
        self.c.demo_positions[r["position_id"]]["last_checked_ms"] = int((time.time() - 600) * 1000)
        self.feed.candles = [(5, 100.2, 97.0)]        # dipped under the 98 stop
        ev = self.c.monitor_demo_positions()["events"]
        self.assertEqual(ev[0]["reason"], "STOP_LOSS")

    def test_rejections(self):
        self.feed.prices["ETHUSDT"] = 100.0
        self.c.last_signals["spot"] = {"symbol": "ETHUSDT", "direction": "SELL"}
        self.assertFalse(self.c.request_demo_spot_trade("ETHUSDT", "spot")["approved"])
        self.c.last_signals["spot"] = signal("ETHUSDT", 100, 98, 104)
        self.feed.prices["ETHUSDT"] = 103.0           # moved >1% away from plan entry
        self.assertIn("moved", self.c.request_demo_spot_trade("ETHUSDT", "spot")["reason"])
        self.feed.prices["ETHUSDT"] = 100.0
        self.assertTrue(self.c.request_demo_spot_trade("ETHUSDT", "spot")["approved"])
        self.assertFalse(self.c.request_demo_spot_trade("ETHUSDT", "spot")["approved"])


class TestAutopilotMarkets(Base):
    def test_autopilot_config_persists_across_backend_restart(self):
        config_path = "config/autopilot-persist.json"
        first = Autopilot(self.c, config_path=config_path)
        first.update({
            "enabled": True,
            "trade_futures": False,
            "risk_pct": 0.35,
        })

        restored = Autopilot(self.c, config_path=config_path)
        self.assertTrue(restored.config["enabled"])
        self.assertFalse(restored.config["trade_futures"])
        self.assertAlmostEqual(restored.config["risk_pct"], 0.35)

    def test_all_agents_are_scanned_when_entry_slots_are_full(self):
        self.c.demo_positions["already-open"] = {
            "symbol": "BTCUSDT", "status": "DEMO_OPEN"}
        calls = []
        def scan(name):
            def run(**kwargs):
                calls.append(name)
                return {"success": True, "scanned": 1, "actionable": 0,
                        "opportunities": [], "rejections": {}}
            return run
        self.c.scan_futures = scan("futures")
        self.c.scan_spot = scan("spot")
        ap = Autopilot(self.c, config_path="config/ap-full.json")
        ap.update({"enabled": True, "max_concurrent": 1,
                   "use_context": False})
        result = ap.tick()
        self.assertEqual(calls, ["futures", "spot"])
        self.assertEqual(result["opened"], [])

    def test_trades_futures_and_spot(self):
        self.feed.prices.update({"BTCUSDT": 100.0, "ETHUSDT": 100.0})

        def opp(domain, symbol, plan_signal):
            return {"symbol": symbol, "direction": "LONG", "confidence": 80,
                    "trade_plan": plan_signal["trade_plan"], "signal": plan_signal,
                    "domain": domain}
        fut = {"symbol": "BTCUSDT", "direction": "LONG", "confidence": 80,
               "trade_plan": {"success": True, "direction": "LONG", "entry": 100,
                              "stop_loss": 99, "take_profit": 102, "reward_risk": 2.0}}
        self.c.scan_futures = lambda limit=12, **k: {
            "success": True, "scanned": 1, "actionable": 1,
            "opportunities": [{**opp("futures", "BTCUSDT", fut)}]}
        self.c.scan_spot = lambda limit=8, **k: {
            "success": True, "scanned": 1, "actionable": 1,
            "opportunities": [opp("spot", "ETHUSDT", signal("ETHUSDT", 100, 98, 104))]}
        ap = Autopilot(self.c, config_path="config/ap.json")
        ap.update({"enabled": True, "max_concurrent": 3, "use_context": False,
                   "risk_pct": 0.1})
        out = ap.tick()
        self.assertEqual(sorted(o["domain"] for o in out["opened"]),
                         ["futures", "spot"], out)
        ap.update({"trade_spot": False})
        self.assertFalse(ap.config["trade_spot"])


if __name__ == "__main__":
    unittest.main()
