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
            {"futures", "spot"},
        )

    def test_market_specific_execution_cost_validation(self):
        plan = {
            "entry": 100, "stop_loss": 99, "take_profit": 102, "atr": 1,
        }
        futures_ok, futures_reason = self.system._validate_demo_entry_price(
            plan, "LONG", 100, market="futures")
        spot_ok, spot_reason = self.system._validate_demo_entry_price(
            plan, "LONG", 100, market="spot")
        self.assertTrue(futures_ok, futures_reason)
        self.assertFalse(spot_ok)
        self.assertIn("reward/risk", spot_reason.lower())

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

    def test_chart_submission_analyzes_only_selected_domain(self):
        calls = []

        def analyze(symbol, preferred_timeframe=None, domains=None):
            calls.append((symbol, preferred_timeframe, domains))
            return {"signals": {"futures": {
                "symbol": symbol,
                "direction": "LONG",
                "confidence": 80,
                "trade_plan": {"success": True, "direction": "LONG", "entry": 100, "take_profit": 102, "stop_loss": 99, "reward_risk": 2.0},
            }}}

        self.system.analyze_live = analyze
        self.system.request_demo_futures_trade = lambda *args, **kwargs: {
            "approved": True, "position_id": "selected-domain-test"
        }

        result = self.system.submit_chart_signal(
            "futures", "BTCUSDT", "5m", 100, 102, 99
        )

        self.assertTrue(result["opened"], result)
        self.assertEqual(calls, [("BTCUSDT", "5m", ["futures"])])

    def test_chart_submission_routes_approved_trade_to_executor(self):
        self.system.analyze_live = lambda symbol, preferred_timeframe=None, domains=None: {
            "signals": {
                "futures": {
                    "symbol": symbol,
                    "direction": "LONG",
                    "confidence": 82,
                    "trade_plan": {
                        "success": True, "direction": "LONG", "entry": 100, "stop_loss": 99, "take_profit": 102, "reward_risk": 2.0,
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

    def test_spot_chart_submission_uses_agent_structure_levels_not_chart_overrides(self):
        self.system.analyze_live = lambda symbol, preferred_timeframe=None, domains=None: {
            "signals": {"spot": {
                "symbol": symbol, "direction": "BUY", "confidence": 82,
                "trade_plan": {"success": True, "direction": "LONG", "entry": 100, "stop_loss": 99, "take_profit": 102, "reward_risk": 2.0},
            }}
        }
        calls = []
        def execute_spot(symbol, domain="spot", signal_override=None):
            calls.append((symbol, domain, signal_override))
            return {"approved": True, "position_id": "spot-chart-test"}
        self.system.request_demo_spot_trade = execute_spot
        result = self.system.submit_chart_signal("spot", "ETHUSDT", "5m", 100, 103, 98)
        self.assertTrue(result["opened"], result)
        self.assertEqual(calls[0][0:2], ("ETHUSDT", "spot"))
        self.assertEqual(calls[0][2]["trade_plan"]["entry"], 100)
        self.assertEqual(calls[0][2]["trade_plan"]["take_profit"], 102)
        self.assertEqual(calls[0][2]["trade_plan"]["stop_loss"], 99)

    def test_chart_submission_does_not_execute_rejected_signal(self):
        self.system.analyze_live = lambda symbol, preferred_timeframe=None, domains=None: {
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
        self.system.analyze_live = lambda symbol, preferred_timeframe=None, domains=None: {
            "signals": {"futures": {
                "symbol": symbol, "direction": "LONG", "confidence": 80,
                "trade_plan": {
                    "success": True, "direction": "LONG",
                    "entry": 100, "stop_loss": 99, "take_profit": 98,
                },
            }}
        }
        self.system.request_demo_futures_trade = lambda *a, **k: self.fail(
            "Invalid proposed levels must not reach execution")
        result = self.system.submit_chart_signal(
            "futures", "BTCUSDT", "1m", 100, 98, 99)
        self.assertEqual(result["decision_status"], "REJECTED")
        self.assertIn("Agent LONG plan", result["decision_reason"])

    def test_spot_accepts_one_minute_chart_timeframe(self):
        self.assertIn("1m", self.system.required_timeframes["spot"])

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

    def test_paper_is_gone_and_live_is_locked(self):
        self.assertFalse(hasattr(self.system, "paper"))
        self.assertEqual(self.system.mode, "DEMO")
        self.assertTrue(self.system.set_mode("DEMO")["success"])
        self.assertFalse(self.system.set_mode("LIVE")["success"])
        self.assertFalse(self.system.set_mode("PAPER")["success"])


    def test_manual_demo_close_moves_trade_to_closed_archive(self):
        from decimal import Decimal

        signal = {
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "confidence": 82,
            "setup_key": "manual-close-regression",
            "trade_plan": {
                "success": True,
                "direction": "LONG",
                "entry": 100,
                "stop_loss": 99,
                "take_profit": 103,
                "atr": 0.5,
                "reward_risk": 2.0,
                "timeframe": "5m",
            },
        }
        self.system._demo_market_price = (
            lambda symbol, market="futures": Decimal("100")
        )

        opened = self.system.request_demo_futures_trade(
            "BTCUSDT", "LONG", signal_override=signal
        )
        self.assertTrue(opened["approved"], opened)
        position_id = opened["position_id"]
        self.assertEqual(
            self.system.demo_positions[position_id]["status"], "DEMO_OPEN"
        )

        # A manual close uses the current executable market quote.
        self.system._demo_market_price = (
            lambda symbol, market="futures": Decimal("101")
        )
        closed = self.system.close_demo_position(position_id)

        self.assertTrue(closed["success"], closed)
        self.assertEqual(
            self.system.demo_positions[position_id]["status"], "DEMO_CLOSED"
        )
        self.assertEqual(
            self.system.demo_positions[position_id]["close_reason"], "MANUAL"
        )

        snapshot = self.system.get_demo_positions()
        self.assertNotIn(
            position_id,
            [item["position_id"] for item in snapshot["open_positions"]],
        )
        archived = [
            item for item in snapshot["closed_positions"]
            if item.get("trade_id") == position_id
        ]
        self.assertTrue(archived, snapshot["closed_positions"])
        self.assertIn(archived[0]["status"], ("CLOSED", "DEMO_CLOSED"))

        # A second request cannot execute the same close twice.
        repeated = self.system.close_demo_position(position_id)
        self.assertFalse(repeated["success"])


    def test_two_demo_positions_can_be_manually_closed_concurrently(self):
        from concurrent.futures import ThreadPoolExecutor
        from decimal import Decimal

        quotes = {"BTCUSDT": "100", "ETHUSDT": "200"}
        self.system._demo_market_price = (
            lambda symbol, market="futures": Decimal(quotes[symbol])
        )
        opened_ids = []

        for symbol, entry, stop, target, atr in (
            ("BTCUSDT", 100, 99, 103, 0.5),
            ("ETHUSDT", 200, 198, 206, 1.0),
        ):
            signal = {
                "symbol": symbol,
                "direction": "LONG",
                "confidence": 82,
                "setup_key": "concurrent-manual-close",
                "trade_plan": {
                    "success": True,
                    "direction": "LONG",
                    "entry": entry,
                    "stop_loss": stop,
                    "take_profit": target,
                    "atr": atr,
                    "reward_risk": 2.0,
                    "timeframe": "5m",
                },
            }
            opened = self.system.request_demo_futures_trade(
                symbol, "LONG", signal_override=signal
            )
            self.assertTrue(opened["approved"], opened)
            opened_ids.append(opened["position_id"])

        quotes.update({"BTCUSDT": "101", "ETHUSDT": "202"})
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(
                self.system.close_demo_position, opened_ids
            ))

        self.assertTrue(all(result["success"] for result in results), results)
        snapshot = self.system.get_demo_positions()
        self.assertEqual(snapshot["open_positions"], [])
        archived_ids = {
            item.get("trade_id") for item in snapshot["closed_positions"]
        }
        self.assertTrue(set(opened_ids).issubset(archived_ids))
        self.assertEqual(
            self.system.risk.get_status()["active_reservations"], 0
        )


    def test_manual_close_is_not_blocked_by_monitor_binance_request(self):
        from concurrent.futures import ThreadPoolExecutor
        from decimal import Decimal
        from threading import Event

        signal = {
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "confidence": 82,
            "setup_key": "manual-close-monitor-priority",
            "trade_plan": {
                "success": True, "direction": "LONG",
                "entry": 100, "stop_loss": 99, "take_profit": 103,
                "atr": 0.5, "reward_risk": 3.0, "timeframe": "5m",
            },
        }
        self.system._demo_market_price = (
            lambda symbol, market="futures": Decimal("100")
        )
        opened = self.system.request_demo_futures_trade(
            "BTCUSDT", "LONG", signal_override=signal
        )
        self.assertTrue(opened["approved"], opened)
        position_id = opened["position_id"]

        monitor_entered = Event()
        release_monitor = Event()

        def slow_monitor_quote(market, symbol):
            monitor_entered.set()
            if not release_monitor.wait(5):
                raise TimeoutError("test monitor quote was not released")
            return {"bid": "100", "ask": "100"}

        self.system.market_feed.fetch_book_ticker = slow_monitor_quote
        self.system._catch_up = lambda *args: None

        with ThreadPoolExecutor(max_workers=2) as pool:
            monitor = pool.submit(
                self.system._monitor_demo_positions_locked, [position_id]
            )
            self.assertTrue(monitor_entered.wait(2), "monitor did not reach Binance quote")
            self.system._demo_market_price = (
                lambda symbol, market="futures": Decimal("101")
            )
            close = pool.submit(self.system.close_demo_position, position_id)
            try:
                result = close.result(timeout=2)
                self.assertTrue(result["success"], result)
            finally:
                release_monitor.set()
            monitor.result(timeout=5)

        self.assertEqual(
            self.system.demo_positions[position_id]["status"], "DEMO_CLOSED"
        )



    def test_futures_scan_analyzes_only_futures_market_data(self):
        self.system.market_scanner.scan_universe = lambda **kwargs: [
            {"symbol": "BTCUSDT", "quote_volume": 100000000}
        ]
        calls = []

        def analyze(symbol, preferred_timeframe=None, domains=None):
            calls.append(domains)
            return {"signals": {"futures": {
                "direction": "WAIT", "confidence": 0,
                "reason": "test signal",
            }}}

        self.system.analyze_live = analyze
        result = self.system.scan_futures(limit=1)
        self.assertTrue(result["success"])
        self.assertEqual(calls, [["futures"]])

    def test_spot_scan_analyzes_only_spot_market_data(self):
        self.system.market_feed._request = lambda market, endpoint, params: [
            {"symbol": "ETHUSDT", "quoteVolume": "30000000", "lastPrice": "100"}
        ]
        calls = []

        def analyze(symbol, preferred_timeframe=None, domains=None):
            calls.append(domains)
            return {"signals": {"spot": {
                "direction": "WAIT", "confidence": 0,
                "reason": "test signal",
            }}}

        self.system.analyze_live = analyze
        result = self.system.scan_spot(limit=1, min_quote_volume=1)
        self.assertTrue(result["success"])
        self.assertEqual(calls, [["spot"]])

if __name__ == "__main__":
    unittest.main()
