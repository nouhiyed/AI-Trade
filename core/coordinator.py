
import math
import threading
import time
from decimal import Decimal
import json
from pathlib import Path
from uuid import uuid4

from agents.futures.agent import FuturesAgent
from agents.spot.agent import SpotAgent

from core.risk_manager import RiskManager
from core.market_data_engine import MarketDataEngine
from core.binance_market_data import BinanceMarketData
from core.market_scanner import FuturesMarketScanner
from core.trade_planner import TradePlanner
from core.demo.database import DemoDatabase
from core.demo.ledger import Ledger
from core.demo.engine import DemoEngine
from core.journal import TradeJournal
from core.learning import LearningEngine, setup_key as make_setup_key
from core.notifier import Notifier
from core.chart_image import render_trade_chart
from core.spot_demo import SpotDemoMixin


class TradingCoordinator(SpotDemoMixin):

    def __init__(self, initial_balance=1000):
        self.risk = RiskManager(initial_balance=initial_balance)
        self.market_feed = BinanceMarketData(timeout=6, total_timeout=6)
        self.market_engine = MarketDataEngine(timeout=6)
        self.market_scanner = FuturesMarketScanner(timeout=6)
        self.trade_planner = TradePlanner()
        # Injected by the API runtime; kept optional for offline/unit-test use.
        self.market_context = None

        self.agents = {
            "futures": FuturesAgent(),
            "spot": SpotAgent()
        }

        self.required_timeframes = {
            "futures": ["1m", "5m", "15m", "1h"],
            "spot": ["1m", "5m", "15m", "1h", "4h"]
        }

        self.last_signals = {}
        self._demo_lock = threading.RLock()
        self._demo_position_locks = {}
        self._demo_position_locks_guard = threading.Lock()
        self.mode = "DEMO"
        self.demo_state_path = Path("config/demo_state.json")
        self.demo_positions = self._load_demo_state()

        self.demo_account_id = "primary"
        self.demo_database = DemoDatabase(Path("data/demo_trading.db"))
        self.demo_ledger = Ledger(database=self.demo_database)
        self.demo_execution = DemoEngine(
            self.demo_database, self.demo_ledger,
            fee_rate=Decimal("0.001"),
            slippage_rate=Decimal("0.0005"),
            futures_fee_rate=Decimal("0.0005"),
            futures_slippage_rate=Decimal("0.0005"),
        )

        account = self.demo_database.connection.execute(
            "SELECT account_id FROM demo_accounts WHERE account_id = ?",
            (self.demo_account_id,),
        ).fetchone()
        if account is None:
            self.demo_execution.create_account(
                self.demo_account_id, initial_balance
            )
        self.journal = TradeJournal(Path("data/journal.db"))
        self.learning = LearningEngine(self.journal)
        self.notifier = Notifier()
        self.max_concurrent_demo = 3
        self._recover_demo_positions()


    def _demo_position_lock(self, position_id):
        key = str(position_id).strip()
        with self._demo_position_locks_guard:
            return self._demo_position_locks.setdefault(key, threading.RLock())

    def _load_demo_state(self):
        try:
            self.demo_state_path.parent.mkdir(parents=True, exist_ok=True)
            data = json.loads(self.demo_state_path.read_text())
            return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception:
            return {}

    def _save_demo_state(self):
        with self._demo_lock:
            self.demo_state_path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.demo_state_path.with_suffix(".tmp")
            temp.write_text(json.dumps(self.demo_positions, indent=2, default=str))
            temp.replace(self.demo_state_path)


    def _recover_demo_positions(self):
        rows = self.demo_execution.get_open_positions(self.demo_account_id)
        changed = False

        # A process may stop after persisting the temporary manual-close state
        # but before the execution transaction. Restore that position on restart.
        for record in self.demo_positions.values():
            if record.get("status") == "DEMO_CLOSING":
                previous = record.pop("closing_previous_status", "DEMO_OPEN")
                if previous not in ("DEMO_OPEN", "DEMO_PARTIALLY_CLOSED",
                                    "DEMO_UNPROTECTED", "DEMO_RECONCILIATION_REQUIRED"):
                    previous = "DEMO_OPEN"
                record["status"] = previous
                record.pop("close_error", None)
                changed = True

        for position in rows:
            engine_id = str(position["position_id"])
            record = next(
                (
                    item for item in self.demo_positions.values()
                    if item.get("engine_position_id") == engine_id
                ),
                None,
            )

            if record is None:
                record = {
                    "position_id": engine_id,
                    "trade_id": engine_id,
                    "engine_position_id": engine_id,
                    "domain": "futures",
                    "execution_source": "INTERNAL_DEMO",
                    "status": "DEMO_RECONCILIATION_REQUIRED",
                }
                self.demo_positions[engine_id] = record
                changed = True

            for key, value in (
                ("symbol", position["symbol"]),
                ("direction", position["direction"]),
                ("quantity", position["initial_quantity"]),
                ("remaining_quantity", position["remaining_quantity"]),
                ("entry_price", position["average_entry_price"]),
                ("leverage", position["leverage"]),
            ):
                value = str(value)
                if record.get(key) != value:
                    record[key] = value
                    changed = True

            db_status = position["status"]
            if db_status == "PARTIALLY_CLOSED":
                status = "DEMO_PARTIALLY_CLOSED"
            elif record.get("stop_loss") is not None and record.get("take_profit") is not None:
                status = "DEMO_OPEN"
            else:
                status = "DEMO_RECONCILIATION_REQUIRED"

            if record.get("status") != status:
                record["status"] = status
                changed = True

        if changed:
            self._save_demo_state()

    def set_mode(self, mode):
        mode = str(mode).strip().upper()
        if mode != "DEMO":
            return {"success": False, "reason": "Only DEMO mode is supported"}
        if any(
            p.get("status") in (
                "DEMO_OPEN", "DEMO_PARTIALLY_CLOSED", "DEMO_CLOSING", "DEMO_UNPROTECTED",
                "DEMO_RECONCILIATION_REQUIRED"
            )
            for p in self.demo_positions.values()
        ):
            return {
                "success": False,
                "reason": "Resolve existing DEMO positions before changing mode"
            }
        self.mode = "DEMO"
        return {"success": True, "mode": self.mode}

    def get_demo_positions(self):
        """Return active positions separately from the closed-trade archive."""
        active_statuses = {
            "DEMO_OPEN", "DEMO_PARTIALLY_CLOSED", "DEMO_CLOSING",
            "DEMO_UNPROTECTED", "DEMO_RECONCILIATION_REQUIRED",
        }
        closed_statuses = {"DEMO_CLOSED", "CLOSED"}
        open_positions = []
        closed_by_id = {}

        for position_id, raw in self.demo_positions.items():
            if not isinstance(raw, dict):
                continue
            record = dict(raw)
            record.setdefault("id", str(position_id))
            record.setdefault("position_id", str(position_id))
            record.setdefault("trade_id", str(position_id))
            status = str(record.get("status", "")).upper()
            if status in active_statuses:
                open_positions.append(record)
            elif status in closed_statuses:
                closed_by_id[str(position_id)] = record

        # The SQLite journal is the durable archive for manual and automatic closes.
        try:
            for trade in self.journal.closed_trades():
                if str(trade.get("status", "")).upper() != "CLOSED":
                    continue
                trade_id = str(trade.get("trade_id", "")).strip()
                if not trade_id:
                    continue
                archived = dict(trade)
                archived.setdefault("id", trade_id)
                archived.setdefault("position_id", trade_id)
                archived.setdefault("close_price", archived.get("exit_price"))
                archived.setdefault("close_reason", archived.get("close_reason") or "CLOSED")
                existing = closed_by_id.get(trade_id)
                if existing is None:
                    closed_by_id[trade_id] = archived
                else:
                    for field, value in archived.items():
                        if existing.get(field) in (None, "", {}):
                            existing[field] = value
        except Exception:
            # State-backed closed trades remain available if journal access fails.
            pass

        closed_positions = sorted(
            closed_by_id.values(),
            key=lambda item: int(item.get("closed_at") or item.get("closed_at_ms") or 0),
            reverse=True,
        )
        result = {
            "mode": self.mode,
            "positions": open_positions,
            "open_positions": open_positions,
            "closed_positions": closed_positions,
        }
        if self.demo_execution is not None and self.demo_account_id is not None:
            result["account_summary"] = self.demo_execution.get_account_summary(
                self.demo_account_id
            )
        return result


    def deposit_demo_balance(self, amount):
        if self.mode != "DEMO":
            return {"success": False, "reason": "DEMO mode is not active"}

        value = Decimal(str(amount))
        if not value.is_finite() or value <= 0:
            return {"success": False, "reason": "Amount must be greater than zero"}

        balance = self.demo_ledger.deposit(
            self.demo_account_id,
            value,
            f"api-deposit:{uuid4().hex}",
        )
        self.risk.sync_balance(
            float(self.demo_execution.get_account_summary(
                self.demo_account_id)["wallet_balance"])
        )
        return {
            "success": True,
            "balance": str(balance),
            "account_summary": self.demo_execution.get_account_summary(
                self.demo_account_id
            ),
        }

    def _demo_market_price(self, symbol, market="futures"):
        quote = self.market_feed.fetch_book_ticker(market, symbol)
        price = Decimal(str(quote["mid_price"]))
        if not price.is_finite() or price <= 0:
            raise ValueError("Invalid live market price")
        market_type = "SPOT" if str(market).lower() == "spot" else "FUTURES"
        self.demo_execution.update_mark_price(
            symbol, market_type, price, source="BINANCE"
        )
        return price

    @staticmethod
    def _apply_close_result(record, result):
        """Accumulate gross PnL and fees over every (partial) close of a position."""
        gross = Decimal(record.get("gross_pnl", "0")) + Decimal(str(result["realized_pnl"]))
        fees = Decimal(record.get("total_fees", record.get("entry_fee", "0"))) + Decimal(str(result["fee"]))
        record["gross_pnl"] = str(gross)
        record["total_fees"] = str(fees)
        record["net_pnl"] = str(gross - fees)

    def _settle_risk(self, position_id, record, reason=None):
        """Release the risk reservation of a fully closed DEMO trade.

        Net result = price PnL minus every fee paid on this trade. It goes to the
        risk engine (balance, daily loss, agent history), to the trade journal
        (learning input) and to the notifier.
        """
        net = float(record.get("net_pnl", "0"))
        record["closed_at_ms"] = int(time.time() * 1000)
        record["exit_price"] = record.get("close_price")
        record["net_pnl"] = str(net)
        record["status"] = "DEMO_CLOSED"
        settled = self.close_trade(position_id, net)
        try:
            # Always merge the final position snapshot into the archive.
            # record_close alone cannot backfill missing SL/TP/entry metadata
            # from the execution state when an older OPEN journal row is incomplete.
            self.journal.record_close(
                position_id, net,
                exit_price=record.get("close_price"),
                reason=reason or record.get("close_reason") or "MANUAL")
            self.journal.record_closed_snapshot(
                record, net, reason or record.get("close_reason") or "MANUAL")
            self._save_demo_state()
            disabled = self.learning.evaluate()
            self._notify_close(record, net, reason)
            for item in disabled:
                self.notifier.send_message(
                    "Learning: setup disabled " + item["setup"] + " - " + item["reason"])
        except Exception as error:
            record["journal_error"] = str(error)
            try:
                self.journal.record_closed_snapshot(
                    record, net, reason or record.get("close_reason") or "MANUAL")
                record.pop("journal_error", None)
                self._save_demo_state()
            except Exception as archive_error:
                record["journal_error"] = str(archive_error)
        if not self.risk.reservations:
            try:
                self.risk.sync_balance(float(
                    self.demo_execution.get_account_summary(
                        self.demo_account_id)["wallet_balance"]))
            except Exception:
                pass
        return settled

    def _notify_close(self, record, net, reason):
        if not self.notifier.enabled:
            return
        text = "%s %s closed (%s)\nNet PnL: %+.4f USDT" % (
            record.get("symbol"), record.get("direction"),
            reason or record.get("close_reason") or "MANUAL", net)
        threading.Thread(target=self.notifier.send_message, args=(text,),
                         daemon=True).start()

    @staticmethod
    def _learning_features(signal):
        """Capture the exact factors visible when this trade was opened."""
        signal = signal or {}
        timeframes = signal.get("timeframes") or {}
        features = {}
        for tf, values in timeframes.items():
            if not isinstance(values, dict):
                continue
            smc = values.get("smc") or {}
            for name in ("bullish_bos", "bearish_bos", "bullish_choch",
                         "bearish_choch", "bullish_sweep", "bearish_sweep",
                         "bullish_fvg", "bearish_fvg", "bullish_ob", "bearish_ob"):
                features[f"{tf}:{name}"] = bool(smc.get(name))
            for factor in ("ema_bull_stack", "ema_bear_stack",
                           "price_above_ema200", "macd_bullish",
                           "macd_bearish", "rsi_bullish_zone",
                           "rsi_bearish_zone"):
                if factor in values:
                    features[f"{tf}:{factor}"] = bool(values.get(factor))
            rsi = values.get("rsi")
            adx = values.get("adx")
            if rsi is not None:
                features[f"{tf}:rsi_present"] = True
                features[f"{tf}:rsi_oversold"] = float(rsi) < 30
                features[f"{tf}:rsi_overbought"] = float(rsi) > 70
                features[f"{tf}:rsi_midrange"] = 40 <= float(rsi) <= 60
            if adx is not None:
                features[f"{tf}:adx_present"] = True
                features[f"{tf}:adx_trending"] = float(adx) >= 20
                features[f"{tf}:adx_strong_trend"] = float(adx) >= 25
        scores = signal.get("scores") or {}
        features["ema_macd_rsi_directional_edge"] = bool(
            scores.get("LONG", scores.get("BUY", 0))
            or scores.get("SHORT", scores.get("SELL", 0))
        )
        orderbook = signal.get("orderbook") or {}
        features["orderbook_used"] = bool(orderbook.get("used"))
        imbalance = orderbook.get("imbalance")
        if imbalance is not None:
            features["orderbook_buy_imbalance"] = float(imbalance) >= 0.15
            features["orderbook_sell_imbalance"] = float(imbalance) <= -0.15
        context = signal.get("market_context") or {}
        details = context.get("details") or {}
        news = details.get("news") or {}
        features["news_present"] = bool(news.get("items"))
        features["news_supports_direction"] = bool(
            news.get("score") and
            (float(news.get("score") or 0) > 0) == (str(signal.get("direction", "")).upper() == "LONG")
        )
        features["whale_flow_present"] = bool(details.get("whales"))
        features["strategy:" + str(signal.get("strategy_tag") or "unclassified")] = True
        return features

    def _validate_demo_entry_price(self, plan, direction, market_price,
                                   min_net_rr=1.5, market="futures"):
        """Reject stale fills that distort structural levels or net reward/risk."""
        try:
            entry = Decimal(str(plan["entry"]))
            stop = Decimal(str(plan["stop_loss"]))
            target = Decimal(str(plan["take_profit"]))
            atr = Decimal(str(plan["atr"]))
            price = Decimal(str(market_price))
            if not all(v.is_finite() and v > 0 for v in (entry, stop, target, atr, price)):
                return False, "Invalid plan or execution price"
            max_drift = max(atr * Decimal("0.10"), entry * Decimal("0.0002"))
            if abs(price - entry) > max_drift:
                return False, "Entry moved more than 0.10 ATR after confirmation; wait for a new setup"
            if str(direction).upper() == "SHORT":
                if not target < price < stop:
                    return False, "Live price invalidated the SHORT structure"
                risk, reward = stop - price, price - target
            else:
                if not stop < price < target:
                    return False, "Live price invalidated the LONG structure"
                risk, reward = price - stop, target - price
            market = str(market).strip().lower()
            if market == "spot":
                fee_rate = self.demo_execution.fee_rate
                slippage_rate = self.demo_execution.slippage_rate
            elif market == "futures":
                fee_rate = self.demo_execution.futures_fee_rate
                slippage_rate = self.demo_execution.futures_slippage_rate
            else:
                return False, "Unknown market cost profile"
            cost = Decimal("2") * (fee_rate + slippage_rate)
            net_reward = reward / price - cost
            net_risk = risk / price + cost
            net_rr = net_reward / net_risk if net_risk > 0 else Decimal("0")
            if net_reward <= 0 or net_rr < Decimal(str(min_net_rr)):
                return False, "Actual execution price reduces net reward/risk below 1.5 after fees and slippage"
            return True, ""
        except (KeyError, TypeError, ValueError, ArithmeticError):
            return False, "Could not validate actual execution against the structural plan"

    @staticmethod
    def _entry_chart_metadata(signal, opened_at_ms):
        """Persist the exact chart candle containing the actual execution time."""
        signal = signal if isinstance(signal, dict) else {}
        plan = signal.get("trade_plan") or {}
        timeframe = str(plan.get("timeframe") or signal.get("timeframe") or "5m").lower()
        seconds = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400}
        interval = seconds.get(timeframe, 300)
        candle_open_ms = (int(opened_at_ms) // (interval * 1000)) * interval * 1000
        return {
            "entry_candle_time": candle_open_ms // 1000,
            "entry_candle_time_ms": candle_open_ms,
            "entry_timeframe": timeframe,
            "entry_origin": str(signal.get("entry_origin") or "AGENT").upper(),
        }

    def _on_demo_open(self, record, signal, reservation):
        """Journal the new trade and (optionally) send a chart snapshot."""
        try:
            plan = signal.get("trade_plan") or {}
            timeframe = (
                signal.get("chart_timeframe")
                or signal.get("timeframe")
                or plan.get("timeframe")
                or "5m"
            )
            record["timeframe"] = str(timeframe).lower()
            context = {
                "confidence": signal.get("confidence"),
                "scores": signal.get("scores"),
                "market_context": signal.get("market_context"),
                "trade_plan": plan,
                "reward_risk": plan.get("reward_risk"),
                "strategy_tag": signal.get("strategy_tag"),
                "features": self._learning_features(signal),
                "timeframe": record["timeframe"],
                "chart_timeframe": record["timeframe"],
            }
            confidence = float(signal.get("confidence") or 0)
            domain = record.get("domain", "futures")
            key = signal.get("setup_key") or make_setup_key(
                record["direction"], confidence,
                context["reward_risk"], domain, signal.get("strategy_tag"))
            record["setup_key"] = key
            record["confidence"] = confidence
            record["risk_amount"] = reservation.get("risk")
            record["context"] = context
            self.journal.record_open(
                record["trade_id"], record.get("domain", "futures"),
                record["symbol"], record["direction"],
                key, confidence, record["entry_price"], record["stop_loss"],
                record["take_profit"], reservation.get("risk"), context)
        except Exception as error:
            record["journal_error"] = str(error)
        if self.notifier.enabled:
            threading.Thread(target=self._send_open_snapshot,
                             args=(dict(record), signal), daemon=True).start()

    def _send_open_snapshot(self, record, signal):
        ctx = signal.get("market_context") or {}
        caption = "%s %s opened (DEMO)\nEntry %s\nSL %s\nTP %s\nConfidence %s\n%s" % (
            record.get("symbol"), record.get("direction"),
            record.get("entry_price"), record.get("stop_loss"),
            record.get("take_profit"), signal.get("confidence"),
            "; ".join(ctx.get("flags", [])))
        try:
            domain = record.get("domain", "futures")
            frame = self.market_feed.fetch_candles(
                "spot" if domain == "spot" else "futures",
                record["symbol"], "5m", limit=90, closed_only=False)
            candles = frame[["open", "high", "low", "close"]].to_dict("records")
            png = render_trade_chart(
                candles, record["direction"], float(record["entry_price"]),
                float(record["stop_loss"]), float(record["take_profit"]),
                record["symbol"])
            if png and self.notifier.send_photo(png, caption):
                return
            # A failed chart fetch or Telegram photo upload must not suppress
            # the essential trade-open notification.
            self.notifier.send_message(caption)
        except Exception as error:
            print("[NOTIFY] snapshot failed:", type(error).__name__)
            self.notifier.send_message(caption)

    def _catch_up(self, record, direction, stop, target):
        """After an outage, replay 1m candles to see if stop/target was touched.

        Returns (reason, level) or None. If one candle touches both levels the
        stop is assumed first (conservative). Candles that opened before the last
        successful check are skipped, so only fully unseen minutes are evaluated.
        """
        since = float(record.get("last_checked_ms") or record.get("opened_at_ms") or 0)
        now_ms = time.time() * 1000
        if not since or now_ms - since < 30_000:
            return None
        limit = min(1000, max(2, int(math.ceil((now_ms - since) / 60_000)) + 2))
        domain = record.get("domain", "futures")
        symbol = str(record["symbol"]).upper()
        frame = self.market_feed.fetch_candles(
            "spot" if domain == "spot" else "futures", symbol, "1m",
            limit=limit, closed_only=False)
        for row in frame.itertuples(index=False):
            if row.open_time.timestamp() * 1000 <= since:
                continue
            low, high = float(row.low), float(row.high)
            if direction == "LONG":
                if low <= float(stop):
                    return "STOP_LOSS", Decimal(str(stop))
                if high >= float(target):
                    return "TAKE_PROFIT", Decimal(str(target))
            else:
                if high >= float(stop):
                    return "STOP_LOSS", Decimal(str(stop))
                if low <= float(target):
                    return "TAKE_PROFIT", Decimal(str(target))
        return None

    def close_demo_position(self, position_id, quantity=None):
        position_id = str(position_id).strip()
        if not position_id:
            return {"success": False, "reason": "Missing position_id"}

        # Serialize actions for this position only. Network price retrieval happens
        # outside the coordinator-wide lock so the monitor cannot delay a manual close.
        with self._demo_position_lock(position_id):
            with self._demo_lock:
                record = self.demo_positions.get(position_id)
                if not record:
                    return {"success": False, "reason": "DEMO position not found"}
                if record.get("status") not in (
                    "DEMO_OPEN", "DEMO_PARTIALLY_CLOSED",
                    "DEMO_UNPROTECTED", "DEMO_RECONCILIATION_REQUIRED"
                ):
                    return {"success": False, "reason": "Position is not closable"}

                previous_status = record.get("status")
                domain = str(record.get("domain", "futures")).lower()
                symbol = str(record.get("symbol", "")).upper()
                record["closing_previous_status"] = previous_status
                record["status"] = "DEMO_CLOSING"
                record.pop("close_error", None)
                self._save_demo_state()

            try:
                # Binance I/O is deliberately outside _demo_lock.
                if domain == "spot":
                    exit_price = self._spot_like_price(domain, symbol, "SELL")
                else:
                    exit_price = self._demo_market_price(symbol)

                with self._demo_lock:
                    result = self._close_demo_position_locked(
                        position_id, quantity, exit_price=exit_price
                    )
                    current = self.demo_positions.get(position_id)
                    if not result.get("success") and current and current.get("status") == "DEMO_CLOSING":
                        current["status"] = previous_status
                        current.pop("closing_previous_status", None)
                        current["close_error"] = result.get("reason", "Close failed")
                        self._save_demo_state()
                    return result
            except Exception as error:
                with self._demo_lock:
                    current = self.demo_positions.get(position_id)
                    if current and current.get("status") == "DEMO_CLOSING":
                        current["status"] = previous_status
                        current.pop("closing_previous_status", None)
                        current["close_error"] = str(error)
                        self._save_demo_state()
                return {"success": False, "reason": str(error)}

    def _close_demo_position_locked(self, position_id, quantity=None, exit_price=None):
        position_id = str(position_id).strip()
        record = self.demo_positions.get(position_id)
        if not record:
            return {"success": False, "reason": "DEMO position not found"}

        if record.get("status") not in (
            "DEMO_OPEN", "DEMO_PARTIALLY_CLOSED", "DEMO_CLOSING",
            "DEMO_UNPROTECTED", "DEMO_RECONCILIATION_REQUIRED"
        ):
            return {"success": False, "reason": "Position is not closable"}

        if record.get("domain") == "spot":
            try:
                result = self._close_spot_like(
                    position_id, record, "MANUAL", exit_price=exit_price
                )
                return {"success": True, "position_id": position_id,
                        "execution": result, "mode": "DEMO"}
            except Exception as error:
                record["close_error"] = str(error)
                self._save_demo_state()
                return {"success": False, "reason": str(error)}

        engine_position_id = record.get("engine_position_id")
        if not engine_position_id:
            return {
                "success": False,
                "reason": "Legacy position requires manual reconciliation; no Binance orders were sent"
            }

        try:
            price = Decimal(str(exit_price)) if exit_price is not None else self._demo_market_price(
                str(record["symbol"]).upper()
            )
            result = self.demo_execution.close_futures_position(
                self.demo_account_id,
                engine_position_id,
                market_price=price,
                quantity=quantity,
                reason="MANUAL",
            )

            record["status"] = (
                "DEMO_CLOSED" if result["status"] == "CLOSED"
                else "DEMO_PARTIALLY_CLOSED"
            )
            record.pop("closing_previous_status", None)
            record["close_price"] = str(result["execution_price"])
            record["realized_pnl"] = str(result["realized_pnl"])
            record["close_fee"] = str(result["fee"])
            record["remaining_quantity"] = str(result["remaining_quantity"])
            self._save_demo_state()

            self._apply_close_result(record, result)
            if record["status"] == "DEMO_CLOSED":
                record["close_reason"] = "MANUAL"
                settled = self._settle_risk(position_id, record, "MANUAL")
                record["risk_settled"] = bool(settled.get("success"))
            else:
                self.risk.update_reservation_status(
                    position_id, record["status"],
                    close_verified=True,
                    realized_pnl=str(result["realized_pnl"]),
                )
            self._save_demo_state()
            return {
                "success": True,
                "position_id": position_id,
                "execution": result,
                "mode": "DEMO",
            }
        except Exception as error:
            record["close_error"] = str(error)
            self._save_demo_state()
            return {"success": False, "reason": str(error)}

    def monitor_demo_positions(self):
        with self._demo_lock:
            position_ids = [
                str(position_id) for position_id, record in self.demo_positions.items()
                if record.get("status") in ("DEMO_OPEN", "DEMO_PARTIALLY_CLOSED")
            ]

        # Each position is monitored independently; Binance I/O for one trade
        # must never hold the global coordinator lock or delay manual closes.
        out = self._monitor_demo_positions_locked(position_ids)
        out["events"] = list(out.get("events", [])) + self._monitor_spot_like()
        return out

    def _monitor_demo_positions_locked(self, position_ids=None):
        """Monitor Futures positions without blocking manual closes during market I/O."""
        results = []
        if position_ids is None:
            with self._demo_lock:
                position_ids = list(self.demo_positions)

        checked = 0
        for position_id in position_ids:
            # Take a consistent snapshot, but never hold the per-position lock
            # while requesting Binance data or replaying candles. Manual close
            # must be able to mark the position DEMO_CLOSING immediately.
            with self._demo_lock:
                record = self.demo_positions.get(position_id)
                if (
                    not record
                    or record.get("status") not in ("DEMO_OPEN", "DEMO_PARTIALLY_CLOSED")
                    or not record.get("engine_position_id")
                ):
                    continue
                checked += 1
                symbol = str(record["symbol"]).upper()
                direction = str(record["direction"]).upper()
                stop = Decimal(str(record["stop_loss"]))
                tp1_done = bool(record.get("tp1_done"))
                target = Decimal(str(
                    record.get("take_profit_2") if tp1_done and record.get("take_profit_2")
                    else record["take_profit"]
                ))
                engine_position_id = record["engine_position_id"]
                snapshot = dict(record)

            try:
                # Network calls stay outside both coordinator and position locks.
                quote = self.market_feed.fetch_book_ticker("futures", symbol)
                exit_price = Decimal(str(
                    quote["ask"] if direction == "SHORT" else quote["bid"]
                ))
                if not exit_price.is_finite() or exit_price <= 0:
                    raise ValueError("Invalid DEMO exit quote")

                try:
                    missed = self._catch_up(snapshot, direction, stop, target)
                except Exception as catch_error:
                    missed = None
                    with self._demo_lock:
                        current = self.demo_positions.get(position_id)
                        if current and current.get("status") in (
                            "DEMO_OPEN", "DEMO_PARTIALLY_CLOSED"
                        ):
                            current["catch_up_error"] = str(catch_error)

                reason = missed[0] if missed else None
                if missed:
                    exit_price = missed[1]
                elif direction == "LONG":
                    if exit_price <= stop:
                        reason = "STOP_LOSS"
                    elif exit_price >= target:
                        reason = "TAKE_PROFIT"
                elif direction == "SHORT":
                    if exit_price >= stop:
                        reason = "STOP_LOSS"
                    elif exit_price <= target:
                        reason = "TAKE_PROFIT"

                # Serialize only the short state/ledger update. If a manual close
                # started while Binance was responding, its DEMO_CLOSING status
                # wins and this stale monitor result is discarded.
                with self._demo_position_lock(position_id):
                    with self._demo_lock:
                        current = self.demo_positions.get(position_id)
                        if (
                            not current
                            or current.get("status") not in (
                                "DEMO_OPEN", "DEMO_PARTIALLY_CLOSED"
                            )
                            or current.get("engine_position_id") != engine_position_id
                        ):
                            continue

                        self.demo_execution.update_mark_price(
                            symbol, "FUTURES", exit_price, source="BINANCE"
                        )
                        current["last_checked_ms"] = int(time.time() * 1000)

                        # Net scalping objective: 3% of original position notional,
                        # after entry fees, estimated exit fees and slippage.
                        if not reason and not current.get("net_profit_partial_done"):
                            entry_price = Decimal(str(current.get("entry_price") or 0))
                            initial_qty = Decimal(str(current.get("quantity") or 0))
                            remaining_qty = Decimal(str(current.get("remaining_quantity") or current.get("quantity") or 0))
                            realized_net = Decimal(str(current.get("net_pnl") or 0))
                            fee_rate = self.demo_execution.futures_fee_rate
                            slip_rate = self.demo_execution.futures_slippage_rate
                            gross_open = ((exit_price - entry_price) if direction == "LONG"
                                          else (entry_price - exit_price)) * remaining_qty
                            estimated_exit_cost = exit_price * remaining_qty * (fee_rate + slip_rate)
                            net_open = realized_net + gross_open - estimated_exit_cost
                            target_net = entry_price * initial_qty * Decimal("0.03")
                            if initial_qty > 0 and net_open >= target_net:
                                reason = ("NET_PROFIT_PARTIAL"
                                          if current.get("take_profit_2") is not None
                                          else "NET_PROFIT_TARGET")

                        if not reason:
                            self._save_demo_state()
                            continue

                        partial_tp1 = (
                            reason in ("TAKE_PROFIT", "NET_PROFIT_PARTIAL")
                            and not current.get("tp1_done")
                            and current.get("take_profit_2") is not None
                        )
                        close_quantity = None
                        close_reason = reason
                        if partial_tp1:
                            remaining = Decimal(str(
                                current.get("remaining_quantity") or current.get("quantity")
                            ))
                            pct = Decimal(str(
                                50 if reason == "NET_PROFIT_PARTIAL"
                                else current.get("tp1_close_pct", 70)
                            ))
                            close_quantity = remaining * pct / Decimal("100")
                            if close_quantity <= 0 or close_quantity >= remaining:
                                partial_tp1 = False
                            else:
                                close_reason = "TAKE_PROFIT_1"

                        result = self.demo_execution.close_futures_position(
                            self.demo_account_id,
                            engine_position_id,
                            market_price=exit_price,
                            quantity=close_quantity,
                            reason=close_reason,
                        )
                        current["status"] = (
                            "DEMO_CLOSED" if result["status"] == "CLOSED"
                            else "DEMO_PARTIALLY_CLOSED"
                        )
                        if partial_tp1 and result["status"] != "CLOSED":
                            current["tp1_done"] = True
                            if reason == "NET_PROFIT_PARTIAL":
                                current["net_profit_partial_done"] = True
                            entry_price = Decimal(str(current["entry_price"]))
                            # Move the stop beyond entry only far enough to
                            # cover this market's estimated round-trip fees/slippage.
                            cost_buffer = Decimal("2") * (
                                self.demo_execution.futures_fee_rate
                                + self.demo_execution.futures_slippage_rate
                            )
                            current["stop_loss"] = str(
                                entry_price * (Decimal("1") - cost_buffer)
                                if direction == "SHORT"
                                else entry_price * (Decimal("1") + cost_buffer)
                            )
                            current["take_profit"] = str(current["take_profit_2"])
                            current["tp1_closed_quantity"] = str(result["closed_quantity"])
                        elif reason == "TAKE_PROFIT" and current.get("tp1_done"):
                            close_reason = "TAKE_PROFIT_2"
                        elif reason == "NET_PROFIT_TARGET":
                            close_reason = "NET_PROFIT_3_PERCENT"
                        current["close_reason"] = close_reason
                        current["close_price"] = str(result["execution_price"])
                        current["realized_pnl"] = str(result["realized_pnl"])
                        current["close_fee"] = str(result["fee"])
                        current["remaining_quantity"] = str(result["remaining_quantity"])
                        self._save_demo_state()

                        try:
                            self._apply_close_result(current, result)
                            if current["status"] == "DEMO_CLOSED":
                                settled = self._settle_risk(position_id, current, reason)
                                current["risk_settled"] = bool(settled.get("success"))
                            else:
                                self.risk.update_reservation_status(
                                    position_id, current["status"],
                                    close_verified=True,
                                    realized_pnl=str(result["realized_pnl"]),
                                )
                            self._save_demo_state()
                        except Exception as risk_error:
                            current["risk_sync_error"] = str(risk_error)
                            self._save_demo_state()

                if reason:
                    results.append({
                        "position_id": position_id,
                        "symbol": symbol,
                        "reason": reason,
                        "result": result,
                    })
            except Exception as error:
                results.append({
                    "position_id": position_id,
                    "symbol": symbol,
                    "error": str(error),
                })

        return {"checked": checked, "events": results}

    @staticmethod
    def select_futures_leverage(signal, plan):
        """Choose conservative leverage from signal strength and ATR volatility."""
        try:
            confidence = float(signal.get("confidence_adjusted",
                                          signal.get("confidence", 0)) or 0)
            entry = float(plan.get("entry") or 0)
            atr = float(plan.get("atr") or 0)
            if entry <= 0 or atr <= 0:
                return 1
            volatility_pct = atr / entry * 100
            if confidence >= 80:
                leverage = 5
            elif confidence >= 70:
                leverage = 3
            elif confidence >= 60:
                leverage = 2
            else:
                leverage = 1
            if volatility_pct >= 2.5:
                leverage = min(leverage, 1)
            elif volatility_pct >= 1.5:
                leverage = min(leverage, 2)
            elif volatility_pct >= 0.8:
                leverage = min(leverage, 3)
            return max(1, min(5, int(leverage)))
        except (TypeError, ValueError, AttributeError):
            return 1

    def request_demo_futures_trade(self, symbol, direction, risk_pct=0.5, leverage=1,
                                   signal_override=None):
        with self._demo_lock:
            return self._request_demo_futures_trade_locked(
                symbol, direction, risk_pct, leverage, signal_override
            )

    def _request_demo_futures_trade_locked(
        self, symbol, direction, risk_pct=0.5, leverage=1, signal_override=None
    ):
        symbol = str(symbol).strip().upper()
        direction = str(direction).strip().upper()

        if self.mode != "DEMO" or self.demo_execution is None:
            return {"approved": False, "reason": "Select DEMO mode first"}

        if not self._agent_enabled("futures"):
            return {"approved": False, "reason": "Futures agent is stopped"}

        if direction not in ("LONG", "SHORT"):
            return {"approved": False, "reason": "Invalid Futures direction"}

        live_statuses = ("DEMO_OPEN", "DEMO_PARTIALLY_CLOSED", "DEMO_CLOSING")
        if any(
            p.get("status") in ("DEMO_UNPROTECTED", "DEMO_RECONCILIATION_REQUIRED")
            for p in self.demo_positions.values()
        ):
            return {"approved": False, "reason": "An unresolved DEMO position exists"}
        active = [p for p in self.demo_positions.values()
                  if p.get("status") in live_statuses]
        if len(active) >= int(self.max_concurrent_demo):
            return {"approved": False, "reason": "Max concurrent DEMO positions reached"}
        if any(str(p.get("symbol")).upper() == symbol for p in active):
            return {"approved": False, "reason": "A DEMO position on this symbol is already open"}

        # Manual chart submissions pass their own analyzed signal so an
        # overlapping autopilot scan cannot replace it between analysis/execution.
        signal = signal_override if isinstance(signal_override, dict) else self.last_signals.get("futures", {})
        if str(signal.get("symbol", "")).upper() != symbol:
            return {"approved": False, "reason": "Symbol does not match latest signal"}
        if str(signal.get("direction", "")).upper() != direction:
            return {"approved": False, "reason": "Direction does not match latest signal"}

        plan = signal.get("trade_plan")
        if not isinstance(plan, dict) or plan.get("success") is not True:
            return {"approved": False, "reason": "No approved Futures trade plan"}
        if str(plan.get("direction", "")).upper() != direction:
            return {"approved": False, "reason": "Trade plan direction mismatch"}

        # Ignore caller-supplied leverage: the backend is the authority.
        leverage = self.select_futures_leverage(signal, plan)

        trade_id = None
        execution_attempted = False
        try:
            entry = Decimal(str(plan["entry"]))
            stop = Decimal(str(plan["stop_loss"]))
            target = Decimal(str(plan["take_profit"]))

            if not all(x.is_finite() and x > 0 for x in (entry, stop, target)):
                raise ValueError("Invalid trade plan prices")
            if direction == "LONG" and not stop < entry < target:
                raise ValueError("Invalid LONG trade plan levels")
            if direction == "SHORT" and not target < entry < stop:
                raise ValueError("Invalid SHORT trade plan levels")

            reservation = self.risk.reserve_trade(
                domain="futures",
                symbol=symbol,
                direction=direction,
                entry=float(entry),
                stop_loss=float(stop),
                risk_pct=float(risk_pct),
                leverage=int(leverage),
            )
            if not reservation.get("approved"):
                return reservation

            trade_id = reservation["trade_id"]
            self.risk.update_reservation_status(trade_id, "DEMO_PENDING")

            market_price = self._demo_market_price(symbol)
            valid_entry, entry_reason = self._validate_demo_entry_price(
                plan, direction, market_price, min_net_rr=1.5, market="futures"
            )
            if not valid_entry:
                self.risk.release_reservation(trade_id)
                return {"approved": False, "mode": "DEMO", "reason": entry_reason}
            if direction == "LONG" and not stop < market_price < target:
                self.risk.release_reservation(trade_id)
                return {
                    "approved": False,
                    "mode": "DEMO",
                    "reason": "Live price is outside the LONG plan range",
                }
            if direction == "SHORT" and not target < market_price < stop:
                self.risk.release_reservation(trade_id)
                return {
                    "approved": False,
                    "mode": "DEMO",
                    "reason": "Live price is outside the SHORT plan range",
                }

            quantity = Decimal(str(reservation["quantity"]))

            execution_attempted = True
            execution = self.demo_execution.open_futures_position(
                self.demo_account_id,
                agent_id="futures",
                symbol=symbol,
                direction=direction,
                quantity=quantity,
                market_price=market_price,
                leverage=Decimal(str(leverage)),
                reference_id=trade_id,
            )

            opened_at_ms = int(time.time() * 1000)
            record = {
                "position_id": trade_id,
                "trade_id": trade_id,
                "engine_position_id": execution["position_id"],
                "domain": "futures",
                "symbol": symbol,
                "direction": direction,
                "quantity": str(execution["quantity"]),
                "entry_price": str(execution["entry_price"]),
                "stop_loss": str(stop),
                "take_profit": str(target),
                "take_profit_2": (
                    str(plan["take_profit_2"]) if plan.get("take_profit_2") else None
                ),
                "structure_support": str(plan["support"]) if plan.get("support") is not None else None,
                "next_support": str(plan["next_support"]) if plan.get("next_support") is not None else None,
                "structure_resistance": str(plan["resistance"]) if plan.get("resistance") is not None else None,
                "next_resistance": str(plan["next_resistance"]) if plan.get("next_resistance") is not None else None,
                "entry_confirmation": str(plan.get("entry_confirmation") or ""),
                "entry_strategy": str(plan.get("entry_strategy") or ""),
                "net_reward_risk": float(plan.get("net_reward_risk", 0)),
                "tp1_close_pct": float(plan.get("tp1_close_pct", 100)),
                "tp1_done": False,
                "remaining_quantity": str(execution["quantity"]),
                "initial_margin": str(execution["initial_margin"]),
                "entry_fee": str(execution["fee"]),
                "status": "DEMO_OPEN",
                "protection_verified": False,
                "execution_source": "INTERNAL_DEMO",
                "total_fees": str(execution["fee"]),
                "opened_at_ms": opened_at_ms,
                **self._entry_chart_metadata(signal, opened_at_ms),
                "last_checked_ms": int(time.time() * 1000),
                "leverage": str(leverage),
            }
            self.demo_positions[trade_id] = record
            self._on_demo_open(record, signal, reservation)
            self._save_demo_state()

            self.risk.update_reservation_status(
                trade_id, "DEMO_OPEN",
                protection_verified=False,
                execution_source="INTERNAL_DEMO",
            )
            return {"approved": True, "mode": "DEMO", **record}

        except Exception as error:
            if trade_id and not execution_attempted:
                self.risk.release_reservation(trade_id)
                return {
                    "approved": False,
                    "mode": "DEMO",
                    "reason": str(error),
                    "execution_submitted": False,
                }
            if trade_id and "Insufficient DEMO cash for margin and fee" in str(error):
                self.risk.release_reservation(trade_id)
                return {
                    "approved": False,
                    "mode": "DEMO",
                    "reason": str(error),
                }
            if trade_id:
                self.risk.update_reservation_status(
                    trade_id, "DEMO_UNPROTECTED",
                    execution_error=str(error),
                )
                self.demo_positions[trade_id] = {
                    "position_id": trade_id,
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "direction": direction,
                    "status": "DEMO_UNPROTECTED",
                    "error": str(error),
                    "execution_source": "INTERNAL_DEMO",
                }
                self._save_demo_state()
            return {
                "approved": False,
                "mode": "DEMO",
                "reason": str(error),
            }

    def _agent_enabled(self, domain):
        domains = self.risk.get_status().get("domains", {})
        return bool(domains.get(domain, {}).get("enabled", False))

    def set_agent_enabled(self, domain, enabled):
        domain = str(domain).strip().lower()
        if domain not in self.agents:
            return {"success": False, "reason": "Unknown agent"}
        self.risk.set_domain(domain, bool(enabled))
        return {"success": True, "domain": domain,
                "enabled": self._agent_enabled(domain)}

    def emergency_stop_agent(self, domain):
        return self.set_agent_enabled(domain, False)

    def resume_agent(self, domain):
        return self.set_agent_enabled(domain, True)

    def emergency_stop_all(self):
        self.risk.emergency_stop()
        return {"success": True, "message": "All agents stopped"}

    def resume_all_agents(self):
        for domain in self.agents:
            self.risk.set_domain(domain, True)
        return {"success": True, "message": "All agents resumed"}

    def get_agent_controls(self):
        return {d: {"enabled": self._agent_enabled(d)} for d in self.agents}

    def analyze_live(self, symbol, preferred_timeframe=None, domains=None):
        symbol = str(symbol).strip().upper()

        if not symbol:
            return {"error": "Symbol cannot be empty"}

        try:
            live_data = self.market_engine.build_live(symbol, domains=domains)
        except Exception as error:
            return {
                "symbol": symbol,
                "source": "binance_rest",
                "signals": {},
                "data_errors": {"market_data": str(error)}
            }

        results = {}
        selected_domains = set(self.agents) if domains is None else set(domains)
        unknown_domains = selected_domains.difference(self.agents)
        if unknown_domains:
            return {"symbol": symbol, "source": "binance_rest", "signals": {},
                    "data_errors": {"domain": "Unknown domain(s): " + ", ".join(sorted(unknown_domains))}}

        for domain, agent in self.agents.items():
            if domain not in selected_domains:
                continue
            if not self._agent_enabled(domain):
                results[domain] = {
                    "status": "STOPPED",
                    "direction": "WAIT",
                    "confidence": 0
                }
                continue
            try:
                agent_data = self.market_engine.for_live_agent(
                    live_data, domain
                )

                signal = agent.analyze(agent_data)
                direction = str(signal.get("direction", "WAIT")).upper() if isinstance(signal, dict) else "WAIT"
                if domain == "futures" and isinstance(signal, dict):
                    if direction in ("LONG", "SHORT"):
                        signal["trade_plan"] = self.trade_planner.create(
                            agent_data, direction, min_reward_risk=1.5,
                            preferred_timeframe=preferred_timeframe,
                            market="futures",
                        )

                if domain == "spot" and isinstance(signal, dict):
                    if str(signal.get("direction", "")).upper() == "BUY":
                        signal["trade_plan"] = self.trade_planner.create(
                            agent_data, "LONG", min_reward_risk=1.5,
                            preferred_timeframe=preferred_timeframe,
                            market="spot",
                        )

                # Strategy tag makes the journal able to compare actual entry styles.
                tf_details = signal.get("timeframes") or {}
                smc_flags = [
                    flag for values in tf_details.values()
                    if isinstance(values, dict)
                    for flag, active in (values.get("smc") or {}).items() if active
                ]
                plan_style = (signal.get("trade_plan") or {}).get("entry_strategy")
                if plan_style:
                    signal["strategy_tag"] = plan_style
                elif any("sweep" in flag for flag in smc_flags) and any("choch" in flag for flag in smc_flags):
                    signal["strategy_tag"] = "liquidity_sweep_reversal"
                elif any("choch" in flag for flag in smc_flags):
                    signal["strategy_tag"] = "market_structure_shift"
                elif any("bos" in flag for flag in smc_flags):
                    signal["strategy_tag"] = "breakout_retest"
                else:
                    signal["strategy_tag"] = "support_resistance_rejection"
                if (self.market_context is not None and
                        isinstance(signal.get("trade_plan"), dict) and
                        signal["trade_plan"].get("success") is True):
                    context_direction = "LONG" if direction == "BUY" else direction
                    assessment = self.market_context.assess(symbol, context_direction)
                    signal["market_context"] = assessment
                    if assessment.get("veto"):
                        signal["trade_plan"] = {
                            **signal["trade_plan"], "success": False,
                            "reason": "Market/news context veto: " + str(assessment["veto"]),
                        }
                results[domain] = signal
                self.last_signals[domain] = signal

            except Exception as error:
                results[domain] = {"error": str(error)}

        return {
            "symbol": symbol,
            "source": live_data.get("source"),
            "signals": results,
            "data_errors": live_data.get("errors", {})
        }


    def submit_chart_signal(
        self, domain, symbol, timeframe,
        entry_price=None, take_profit=None, stop_loss=None
    ):
        """Review user-proposed chart levels; only an agent-approved plan can reach DEMO execution."""
        domain = str(domain).strip().lower()
        symbol = str(symbol).strip().upper()
        timeframe = str(timeframe).strip().lower()
        allowed_timeframes = {
            "futures": {"1m", "5m", "15m", "1h"},
            "spot": {"1m", "5m", "15m", "1h", "4h"},
        }
        base = {
            "success": False, "opened": False, "domain": domain,
            "symbol": symbol, "timeframe": timeframe,
        }
        if domain not in self.agents:
            return {**base, "decision_status": "REJECTED",
                    "decision_reason": "Unknown agent", "reason": "Unknown agent"}
        if not symbol or not symbol.endswith("USDT"):
            return {**base, "decision_status": "REJECTED",
                    "decision_reason": "Invalid USDT symbol", "reason": "Invalid USDT symbol"}
        if timeframe not in allowed_timeframes[domain]:
            return {**base, "decision_status": "REJECTED",
                    "decision_reason": "Unsupported timeframe for this agent",
                    "reason": "Unsupported timeframe for this agent"}
        if not self._agent_enabled(domain):
            reason = domain.title() + " agent is stopped"
            return {**base, "decision_status": "REJECTED",
                    "decision_reason": reason, "reason": reason}

        # A chart submission belongs to one selected market/agent. Do not
        # fetch the other market or run its agent on this request.
        analysis = self.analyze_live(
            symbol, preferred_timeframe=timeframe, domains=[domain]
        )
        signal = analysis.get("signals", {}).get(domain, {})
        if not isinstance(signal, dict) or signal.get("error"):
            reason = (signal.get("error") if isinstance(signal, dict) else None) or "Analysis unavailable"
            return {**base, "success": True, "decision_status": "REJECTED",
                    "decision_reason": str(reason), "reason": str(reason),
                    "analysis": analysis}

        signal = dict(signal)
        signal.setdefault("symbol", symbol)
        signal["chart_timeframe"] = timeframe
        market_context = signal.get("market_context") or {}
        if market_context.get("veto"):
            reason = "News/market context veto: " + str(market_context["veto"])
            return {**base, "success": True, "decision_status": "REJECTED",
                    "decision_reason": reason, "reason": reason, "signal": signal}
        signal["chart_market"] = domain
        direction = str(signal.get("direction", "WAIT")).strip().upper()
        if domain == "futures":
            is_long = direction == "LONG"
            is_short = direction == "SHORT"
            if not (is_long or is_short):
                reason = signal.get("reason") or "Futures agent returned WAIT: no directional edge"
                return {**base, "success": True, "decision_status": "REJECTED",
                        "decision_reason": str(reason), "reason": str(reason),
                        "signal": signal}
        elif domain == "spot":
            if direction != "BUY":
                reason = signal.get("reason") or domain.title() + " agent did not approve a BUY setup"
                return {**base, "success": True, "decision_status": "REJECTED",
                        "decision_reason": str(reason), "reason": str(reason),
                        "signal": signal}
            is_long, is_short = True, False

        # Chart prices are reference annotations only. The execution levels must
        # come from the same structure-rejection planner used by autopilot.
        agent_plan = signal.get("trade_plan") or {}
        if not isinstance(agent_plan, dict) or agent_plan.get("success") is not True:
            reason = (agent_plan.get("reason") if isinstance(agent_plan, dict) else None) or (
                "No confirmed support/resistance rejection; agent must wait")
            return {**base, "success": True, "decision_status": "REJECTED",
                    "decision_reason": str(reason), "reason": str(reason),
                    "signal": signal, "trade_plan": agent_plan}

        try:
            proposed = {
                "entry": Decimal(str(entry_price)),
                "take_profit": Decimal(str(take_profit)),
                "stop_loss": Decimal(str(stop_loss)),
            }
        except Exception:
            reason = "Chart reference prices must be numeric"
            return {**base, "success": True, "decision_status": "REJECTED",
                    "decision_reason": reason, "reason": reason,
                    "signal": signal, "trade_plan": agent_plan}
        if not all(value.is_finite() and value > 0 for value in proposed.values()):
            reason = "Chart reference prices must be finite positive numbers"
            return {**base, "success": True, "decision_status": "REJECTED",
                    "decision_reason": reason, "reason": reason,
                    "signal": signal, "trade_plan": agent_plan}

        try:
            entry = Decimal(str(agent_plan["entry"]))
            target = Decimal(str(agent_plan["take_profit"]))
            stop = Decimal(str(agent_plan["stop_loss"]))
        except (KeyError, TypeError, ValueError):
            reason = "Agent structure plan is missing entry, target or stop"
            return {**base, "success": True, "decision_status": "REJECTED",
                    "decision_reason": reason, "reason": reason,
                    "signal": signal, "trade_plan": agent_plan}
        if not all(value.is_finite() and value > 0 for value in (entry, target, stop)):
            reason = "Agent structure plan contains invalid prices"
            return {**base, "success": True, "decision_status": "REJECTED",
                    "decision_reason": reason, "reason": reason,
                    "signal": signal, "trade_plan": agent_plan}
        if is_long and not stop < entry < target:
            reason = "Agent LONG plan must place stop below entry and target above entry"
            return {**base, "success": True, "decision_status": "REJECTED",
                    "decision_reason": reason, "reason": reason,
                    "signal": signal, "trade_plan": agent_plan}
        if is_short and not target < entry < stop:
            reason = "Agent SHORT plan must place target below entry and stop above entry"
            return {**base, "success": True, "decision_status": "REJECTED",
                    "decision_reason": reason, "reason": reason,
                    "signal": signal, "trade_plan": agent_plan}

        risk_distance = abs(entry - stop)
        reward_distance = abs(target - entry)
        reward_risk = reward_distance / risk_distance if risk_distance else Decimal("0")
        if reward_risk < Decimal("1.0"):
            reason = "Agent structure target has reward/risk below 1.0"
            return {**base, "success": True, "decision_status": "REJECTED",
                    "decision_reason": reason, "reason": reason,
                    "signal": signal, "trade_plan": agent_plan,
                    "proposed_levels": {k: str(v) for k, v in proposed.items()},
                    "reward_risk": float(reward_risk)}

        plan = dict(agent_plan)
        plan.update({
            "success": True, "direction": "SHORT" if is_short else "LONG",
            "entry": float(entry), "stop_loss": float(stop),
            "take_profit": float(target), "reward_risk": round(float(reward_risk), 4),
            "timeframe": timeframe,
            "method": "AGENT_STRUCTURE_REJECTION_PLAN",
            "chart_reference_levels": {k: str(v) for k, v in proposed.items()},
        })
        signal["trade_plan"] = plan
        self.last_signals[domain] = signal

        try:
            if domain == "futures":
                execution = self.request_demo_futures_trade(
                    symbol, direction, signal_override=signal
                )
            else:
                execution = self.request_demo_spot_trade(
                    symbol, domain=domain, signal_override=signal
                )
            opened = bool(execution.get("approved"))
            reason = (
                "Agent accepted the setup and DEMO risk/execution checks passed"
                if opened else str(execution.get("reason", "Risk or execution checks rejected the setup"))
            )
            status = "APPROVED" if opened else "REJECTED"
        except Exception as error:
            execution = {"approved": False, "reason": str(error)}
            opened = False
            reason = str(error)
            status = "REJECTED"

        return {
            **base, "success": True, "opened": opened,
            "decision_status": status, "decision_reason": reason,
            "decision": status + ": " + reason,
            "signal": signal, "trade_plan": plan, "execution": execution,
            "proposed_levels": {k: str(v) for k, v in proposed.items()},
        }

    def scan_futures(self, limit=12, min_quote_volume=None):
        """Scan liquid USDT perpetuals and rank actionable Futures signals."""
        if not self._agent_enabled("futures"):
            return {
                "success": False,
                "reason": "Futures agent is stopped",
                "opportunities": [],
            }

        try:
            universe = self.market_scanner.scan_universe(
                limit=limit,
                min_quote_volume=min_quote_volume,
            )
        except Exception as error:
            return {
                "success": False,
                "reason": "Market universe scan failed: " + str(error),
                "opportunities": [],
            }

        opportunities = []
        errors = {}
        rejections = {}
        rejection_samples = []

        def reject(reason, symbol):
            key = str(reason or "No actionable signal")
            rejections[key] = rejections.get(key, 0) + 1
            if len(rejection_samples) < 12:
                rejection_samples.append({"symbol": symbol, "reason": key})

        for item in universe:
            symbol = item["symbol"]
            try:
                analysis = self.analyze_live(symbol, domains=["futures"])
                signal = analysis.get("signals", {}).get("futures", {})
                if not isinstance(signal, dict):
                    reject("Missing Futures analysis", symbol)
                    continue

                direction = str(signal.get("direction", "WAIT")).upper()
                confidence = float(signal.get("confidence", 0) or 0)

                if direction not in ("LONG", "SHORT"):
                    reject(signal.get("reason") or "Signal is WAIT", symbol)
                    continue

                trade_plan = signal.get("trade_plan")
                if not isinstance(trade_plan, dict):
                    reject("Trade plan was not generated", symbol)
                    continue
                if trade_plan.get("success") is not True:
                    reject(trade_plan.get("reason") or "Trade plan rejected", symbol)
                    continue

                opportunities.append({
                    **item,
                    "direction": direction,
                    "confidence": confidence,
                    "trade_plan": trade_plan,
                    "signal": signal,
                })
            except Exception as error:
                errors[symbol] = str(error)

        opportunities.sort(
            key=lambda item: (
                item["confidence"],
                item["quote_volume"],
            ),
            reverse=True,
        )

        # Keep the selected symbol's signal as the latest Futures signal.
        if opportunities:
            self.last_signals["futures"] = opportunities[0]["signal"]

        return {
            "success": True,
            "scanned": len(universe),
            "actionable": len(opportunities),
            "selected": (
                opportunities[0]["symbol"] if opportunities else None
            ),
            "opportunities": opportunities,
            "errors": errors,
            "rejections": rejections,
            "rejection_samples": rejection_samples,
        }

    def analyze_all(self, market_data):
        results = {}

        if not isinstance(market_data, dict):
            return {"error": "Invalid market_data"}

        nested = isinstance(market_data.get("timeframes"), dict)

        for domain, agent in self.agents.items():
            if not self._agent_enabled(domain):
                results[domain] = {
                    "status": "STOPPED",
                    "direction": "WAIT",
                    "confidence": 0
                }
                continue
            try:
                if nested:
                    agent_data = self.market_engine.for_agent(
                        market_data, domain
                    )
                else:
                    agent_data = {
                        "symbol": market_data.get("symbol", "UNKNOWN"),
                        "orderbook": market_data.get("orderbook", {})
                    }

                    for tf in self.required_timeframes[domain]:
                        if tf in market_data:
                            agent_data[tf] = market_data[tf]

                signal = agent.analyze(agent_data)
                results[domain] = signal
                self.last_signals[domain] = signal

            except Exception as error:
                results[domain] = {"error": str(error)}

        return results

    def request_trade(
        self, domain, symbol, direction, entry,
        stop_loss, risk_pct=0.5, leverage=1
    ):
        if domain not in self.agents:
            return {"approved": False, "reason": "Unknown agent"}
        if not self._agent_enabled(domain):
            return {"approved": False, "reason": "Agent is stopped"}

        signal = self.last_signals.get(domain, {})

        if signal.get("direction") != direction:
            return {
                "approved": False,
                "reason": "Direction does not match latest signal"
            }

        if signal.get("symbol") != symbol:
            return {
                "approved": False,
                "reason": "Symbol does not match latest signal"
            }

        return self.risk.reserve_trade(
            domain=domain,
            symbol=symbol,
            direction=direction,
            entry=entry,
            stop_loss=stop_loss,
            risk_pct=risk_pct,
            leverage=leverage
        )

    def close_trade(self, trade_id, realized_pnl):
        result = self.risk.close_trade(trade_id, realized_pnl)

        if result.get("success"):
            domain = trade_id.split("_")[0]

            if domain in self.agents:
                self.agents[domain].record_trade({
                    "trade_id": trade_id,
                    "result": (
                        "WIN" if realized_pnl > 0
                        else "LOSS" if realized_pnl < 0
                        else "BREAKEVEN"
                    ),
                    "realized_pnl": realized_pnl
                })

        return result

    def get_system_status(self):
        return {
            "risk": self.risk.get_status(),
            "mode": self.mode,
            "demo": self.get_demo_positions(),
            "agents": {
                domain: agent.get_performance()
                for domain, agent in self.agents.items()
            },
            "last_signals": self.last_signals
        }

    def emergency_stop(self):
        return self.emergency_stop_all()

