
import math
import threading
import time
from decimal import Decimal
import json
from pathlib import Path
from uuid import uuid4

from agents.futures.agent import FuturesAgent
from agents.spot.agent import SpotAgent
from agents.alpha.agent import AlphaAgent

from core.risk_manager import RiskManager
from core.market_data_engine import MarketDataEngine
from core.token_safety_engine import TokenSafetyEngine
from core.binance_market_data import BinanceMarketData
from core.market_scanner import FuturesMarketScanner
from core.trade_planner import TradePlanner
from core.binance_execution import BinanceExecutionEngine
from core.demo.database import DemoDatabase
from core.demo.ledger import Ledger
from core.demo.engine import DemoEngine
from core.journal import TradeJournal
from core.learning import LearningEngine, setup_key as make_setup_key
from core.notifier import Notifier
from core.chart_image import render_trade_chart
from core.alpha_feed import AlphaFeed
from core.spot_demo import SpotDemoMixin


class TradingCoordinator(SpotDemoMixin):

    def __init__(self, initial_balance=1000):
        self.risk = RiskManager(initial_balance=initial_balance)
        self.market_feed = BinanceMarketData(timeout=6)
        self.market_engine = MarketDataEngine()
        self.market_scanner = FuturesMarketScanner()
        self.trade_planner = TradePlanner()
        self.safety_engine = TokenSafetyEngine()

        self.agents = {
            "futures": FuturesAgent(),
            "spot": SpotAgent(),
            "alpha": AlphaAgent()
        }

        self.required_timeframes = {
            "futures": ["1m", "5m", "15m", "1h"],
            "spot": ["5m", "15m", "1h", "4h"],
            "alpha": ["5m", "15m", "1h"]
        }

        self.last_signals = {}
        self._demo_lock = threading.RLock()
        self.alpha_config_path = Path("config/alpha_tokens.json")
        self.mode = "DEMO"
        self.demo_state_path = Path("config/demo_state.json")
        self.demo_positions = self._load_demo_state()

        self.demo_account_id = "primary"
        self.demo_database = DemoDatabase(Path("data/demo_trading.db"))
        self.demo_ledger = Ledger(database=self.demo_database)
        self.demo_execution = DemoEngine(
            self.demo_database, self.demo_ledger
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
        self.alpha_feed = AlphaFeed()
        self.max_concurrent_demo = 3
        self._recover_demo_positions()


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
        self.demo_state_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.demo_state_path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.demo_positions, indent=2, default=str))
        temp.replace(self.demo_state_path)


    def _recover_demo_positions(self):
        rows = self.demo_execution.get_open_positions(self.demo_account_id)
        changed = False

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
                "DEMO_OPEN", "DEMO_PARTIALLY_CLOSED", "DEMO_UNPROTECTED",
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
        result = {
            "mode": self.mode,
            "positions": list(self.demo_positions.values())
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
        settled = self.close_trade(position_id, net)
        try:
            self.journal.record_close(
                position_id, net,
                exit_price=record.get("close_price"),
                reason=reason or record.get("close_reason") or "MANUAL")
            disabled = self.learning.evaluate()
            self._notify_close(record, net, reason)
            for item in disabled:
                self.notifier.send_message(
                    "Learning: setup disabled " + item["setup"] + " - " + item["reason"])
        except Exception as error:
            record["journal_error"] = str(error)
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

    def _on_demo_open(self, record, signal, reservation):
        """Journal the new trade and (optionally) send a chart snapshot."""
        try:
            context = {
                "confidence": signal.get("confidence"),
                "scores": signal.get("scores"),
                "market_context": signal.get("market_context"),
                "reward_risk": (signal.get("trade_plan") or {}).get("reward_risk"),
            }
            confidence = float(signal.get("confidence") or 0)
            domain = record.get("domain", "futures")
            key = signal.get("setup_key") or make_setup_key(
                record["direction"], confidence,
                context["reward_risk"], domain)
            record["setup_key"] = key
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
        try:
            domain = record.get("domain", "futures")
            if domain == "alpha":
                frame = self.market_feed.fetch_alpha_candles(
                    record["symbol"], "5m", limit=90)
            else:
                frame = self.market_feed.fetch_candles(
                    "spot" if domain == "spot" else "futures",
                    record["symbol"], "5m", limit=90, closed_only=False)
            candles = frame[["open", "high", "low", "close"]].to_dict("records")
            png = render_trade_chart(
                candles, record["direction"], float(record["entry_price"]),
                float(record["stop_loss"]), float(record["take_profit"]),
                record["symbol"])
            ctx = signal.get("market_context") or {}
            caption = "%s %s (DEMO)\nEntry %s\nSL %s\nTP %s\nConfidence %s\n%s" % (
                record["symbol"], record["direction"], record["entry_price"],
                record["stop_loss"], record["take_profit"],
                signal.get("confidence"), "; ".join(ctx.get("flags", [])))
            if png:
                self.notifier.send_photo(png, caption)
            else:
                self.notifier.send_message(caption)
        except Exception as error:
            print("[NOTIFY] snapshot failed:", error)

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
        if domain == "alpha":
            frame = self.market_feed.fetch_alpha_candles(symbol, "1m", limit=limit)
        else:
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
        with self._demo_lock:
            return self._close_demo_position_locked(position_id, quantity)

    def _close_demo_position_locked(self, position_id, quantity=None):
        position_id = str(position_id).strip()
        record = self.demo_positions.get(position_id)
        if not record:
            return {"success": False, "reason": "DEMO position not found"}

        if record.get("status") not in (
            "DEMO_OPEN", "DEMO_PARTIALLY_CLOSED",
            "DEMO_UNPROTECTED", "DEMO_RECONCILIATION_REQUIRED"
        ):
            return {"success": False, "reason": "Position is not closable"}

        if record.get("domain") in ("spot", "alpha"):
            try:
                result = self._close_spot_like(position_id, record, "MANUAL")
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
            symbol = str(record["symbol"]).upper()
            price = self._demo_market_price(symbol)
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
            out = self._monitor_demo_positions_locked()
            out["events"] = list(out.get("events", [])) + self._monitor_spot_like()
            return out

    def _monitor_demo_positions_locked(self):
        """Monitor internal DEMO Futures positions using live Binance quotes."""
        results = []
        positions = [
            (position_id, record)
            for position_id, record in self.demo_positions.items()
            if record.get("status") in ("DEMO_OPEN", "DEMO_PARTIALLY_CLOSED")
            and record.get("engine_position_id")
        ]
        price_cache = {}

        for position_id, record in positions:
            try:
                symbol = str(record["symbol"]).upper()
                if symbol not in price_cache:
                    quote = self.market_feed.fetch_book_ticker(
                        "futures", symbol
                    )
                    price_cache[symbol] = quote

                quote = price_cache[symbol]
                direction = str(record["direction"]).upper()
                exit_price = Decimal(str(
                    quote["ask"] if direction == "SHORT" else quote["bid"]
                ))
                if not exit_price.is_finite() or exit_price <= 0:
                    raise ValueError("Invalid DEMO exit quote")

                self.demo_execution.update_mark_price(
                    symbol, "FUTURES", exit_price, source="BINANCE"
                )

                stop = Decimal(str(record["stop_loss"]))
                target = Decimal(str(record["take_profit"]))
                reason = None
                checked_ok = True

                # 1) replay candles missed while the app/network was down
                try:
                    missed = self._catch_up(record, direction, stop, target)
                except Exception as catch_error:
                    missed = None
                    checked_ok = False
                    record["catch_up_error"] = str(catch_error)
                if missed:
                    reason, exit_price = missed

                # 2) live quote check
                if reason is None:
                    if direction == "LONG":
                        if exit_price <= stop:
                            reason = "STOP_LOSS"
                        elif exit_price >= target:
                            reason = "TAKE_PROFIT"
                    elif direction == "SHORT":
                        if exit_price >= stop:
                            reason = "STOP_LOSS"
                        elif exit_price <= target:
                            reason = "TAKE_PROFIT"

                if checked_ok:
                    record["last_checked_ms"] = int(time.time() * 1000)

                if reason:
                    result = self.demo_execution.close_futures_position(
                        self.demo_account_id,
                        record["engine_position_id"],
                        market_price=exit_price,
                        reason=reason,
                    )
                    record["status"] = (
                        "DEMO_CLOSED" if result["status"] == "CLOSED"
                        else "DEMO_PARTIALLY_CLOSED"
                    )
                    record["close_reason"] = reason
                    record["close_price"] = str(result["execution_price"])
                    record["realized_pnl"] = str(result["realized_pnl"])
                    record["close_fee"] = str(result["fee"])
                    record["remaining_quantity"] = str(
                        result["remaining_quantity"]
                    )
                    self._save_demo_state()

                    try:
                        self._apply_close_result(record, result)
                        if record["status"] == "DEMO_CLOSED":
                            settled = self._settle_risk(position_id, record, reason)
                            record["risk_settled"] = bool(settled.get("success"))
                        else:
                            self.risk.update_reservation_status(
                                position_id,
                                record["status"],
                                close_verified=True,
                                realized_pnl=str(result["realized_pnl"]),
                            )
                        self._save_demo_state()
                    except Exception as risk_error:
                        record["risk_sync_error"] = str(risk_error)
                        self._save_demo_state()

                    results.append({
                        "position_id": position_id,
                        "symbol": symbol,
                        "reason": reason,
                        "result": result,
                    })
            except Exception as error:
                results.append({
                    "position_id": position_id,
                    "symbol": record.get("symbol"),
                    "error": str(error),
                })

        return {"checked": len(positions), "events": results}

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

    def request_demo_futures_trade(self, symbol, direction, risk_pct=0.5, leverage=1):
        with self._demo_lock:
            return self._request_demo_futures_trade_locked(symbol, direction, risk_pct, leverage)

    def _request_demo_futures_trade_locked(
        self, symbol, direction, risk_pct=0.5, leverage=1
    ):
        symbol = str(symbol).strip().upper()
        direction = str(direction).strip().upper()

        if self.mode != "DEMO" or self.demo_execution is None:
            return {"approved": False, "reason": "Select DEMO mode first"}

        if not self._agent_enabled("futures"):
            return {"approved": False, "reason": "Futures agent is stopped"}

        if direction not in ("LONG", "SHORT"):
            return {"approved": False, "reason": "Invalid Futures direction"}

        live_statuses = ("DEMO_OPEN", "DEMO_PARTIALLY_CLOSED")
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

        signal = self.last_signals.get("futures", {})
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
            if abs(market_price - entry) / entry > Decimal("0.01"):
                self.risk.release_reservation(trade_id)
                return {
                    "approved": False,
                    "mode": "DEMO",
                    "reason": "Market price moved more than 1% from the approved plan entry",
                }
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
                "initial_margin": str(execution["initial_margin"]),
                "entry_fee": str(execution["fee"]),
                "status": "DEMO_OPEN",
                "protection_verified": False,
                "execution_source": "INTERNAL_DEMO",
                "total_fees": str(execution["fee"]),
                "opened_at_ms": int(time.time() * 1000),
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

    def _get_alpha_safety(self, symbol):
        unknown = {
            "status": "UNKNOWN",
            "passed": False,
            "critical": False
        }

        try:
            with open(self.alpha_config_path, "r") as f:
                config = json.load(f)

            if config.get("enabled") is not True:
                return unknown

            tokens = config.get("tokens", [])

            token = next(
                (
                    x for x in tokens
                    if isinstance(x, dict)
                    and str(x.get("symbol", "")).upper()
                    == str(symbol).upper()
                ),
                None
            )

            if not token:
                return unknown

            chain = token.get("chain")
            address = token.get("address")

            if not chain or not address:
                return unknown

            result = self.safety_engine.check_token(
                chain, address
            )

            return result if isinstance(result, dict) else unknown

        except Exception:
            return unknown


    def analyze_live(self, symbol, preferred_timeframe=None):
        symbol = str(symbol).strip().upper()

        if not symbol:
            return {"error": "Symbol cannot be empty"}

        try:
            live_data = self.market_engine.build_live(symbol)
        except Exception as error:
            return {
                "symbol": symbol,
                "source": "binance_rest",
                "signals": {},
                "data_errors": {"market_data": str(error)}
            }

        results = {}

        for domain, agent in self.agents.items():
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

                if domain == "alpha":
                    agent_data["token_safety"] = (
                        self._get_alpha_safety(symbol)
                    )

                signal = agent.analyze(agent_data)
                if domain == "futures" and isinstance(signal, dict):
                    direction = str(signal.get("direction", "WAIT")).upper()
                    if direction in ("LONG", "SHORT"):
                        signal["trade_plan"] = self.trade_planner.create(
                            agent_data, direction,
                            preferred_timeframe=preferred_timeframe,
                        )

                if domain == "spot" and isinstance(signal, dict):
                    if str(signal.get("direction", "")).upper() == "BUY":
                        signal["trade_plan"] = self.trade_planner.create(
                            agent_data, "LONG",
                            preferred_timeframe=preferred_timeframe,
                        )

                if domain == "alpha" and isinstance(signal, dict):
                    signal["execution_enabled"] = (
                        self.mode == "DEMO"
                        and str(agent_data["token_safety"].get("status", "")).upper() == "PASS"
                    )

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


    def submit_chart_signal(self, domain, symbol, timeframe):
        """Send a chart opportunity to its agent; open only after full agent and risk approval."""
        domain = str(domain).strip().lower()
        symbol = str(symbol).strip().upper()
        timeframe = str(timeframe).strip().lower()
        allowed_timeframes = {
            "futures": {"1m", "5m", "15m", "1h", "4h"},
            "spot": {"5m", "15m", "1h", "4h"},
            "alpha": {"5m", "15m", "1h"},
        }
        if domain not in self.agents:
            return {"success": False, "reason": "Unknown agent", "opened": False}
        if not symbol or not symbol.endswith("USDT"):
            return {"success": False, "reason": "Invalid USDT symbol", "opened": False}
        if timeframe not in allowed_timeframes[domain]:
            return {"success": False, "reason": "Unsupported timeframe for this agent",
                    "opened": False}
        if not self._agent_enabled(domain):
            return {"success": False, "reason": domain.title() + " agent is stopped",
                    "opened": False}

        analysis = self.analyze_live(symbol, preferred_timeframe=timeframe)
        signal = analysis.get("signals", {}).get(domain, {})
        if domain == "alpha":
            try:
                token = self.alpha_feed.token(symbol)
                signal = self.analyze_alpha(token, preferred_timeframe=timeframe)
            except Exception as error:
                return {"success": False, "reason": "Alpha analysis failed: " + str(error),
                        "opened": False}
        if not isinstance(signal, dict):
            return {"success": False, "reason": "Analysis unavailable",
                    "opened": False, "analysis": analysis}
        if signal.get("error"):
            return {"success": False, "reason": signal.get("error"),
                    "opened": False, "analysis": analysis}
        signal = dict(signal)
        signal["chart_timeframe"] = timeframe
        signal["chart_market"] = domain
        if domain == "alpha":
            safety = signal.get("token_safety") or {
                "status": "UNKNOWN", "passed": False, "critical": False}
            signal["token_safety"] = safety
            signal["execution_enabled"] = (
                self.mode == "DEMO"
                and str(safety.get("status", "")).upper() == "PASS"
            )
            self.last_signals[domain] = signal
        plan = signal.get("trade_plan")
        safety = signal.get("token_safety") or {}
        execution = None
        opened = False
        if domain == "alpha" and str(safety.get("status", "")).upper() != "PASS":
            decision = "REJECTED: Alpha token safety is not PASS"
        elif domain == "futures" and signal.get("direction") not in ("LONG", "SHORT"):
            decision = "REJECTED: Agent returned WAIT"
        elif domain == "spot" and signal.get("direction") != "BUY":
            decision = "REJECTED: Spot agent did not return BUY"
        elif not isinstance(plan, dict) or plan.get("success") is not True:
            decision = "REJECTED: " + str((plan or {}).get("reason", "No valid trade plan"))
        else:
            try:
                if domain == "futures":
                    execution = self.request_demo_futures_trade(
                        symbol, signal["direction"])
                else:
                    execution = self.request_demo_spot_trade(
                        symbol, domain=domain)
                opened = bool(execution.get("approved"))
                decision = (
                    "APPROVED: DEMO position opened"
                    if opened else
                    "REJECTED: " + str(execution.get("reason", "Risk or execution check failed"))
                )
            except Exception as error:
                execution = {"approved": False, "reason": str(error)}
                opened = False
                decision = "REJECTED: " + str(error)
        if execution is None:
            execution = {"approved": False, "reason": decision}
        return {
            "success": True,
            "opened": opened,
            "domain": domain,
            "symbol": symbol,
            "timeframe": timeframe,
            "decision": decision,
            "signal": signal,
            "trade_plan": plan,
            "execution": execution,
            "token_safety": safety if domain == "alpha" else None,
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
                analysis = self.analyze_live(symbol)
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

                if domain == "alpha":
                    agent_data["token_safety"] = (
                        self._get_alpha_safety(
                            agent_data.get("symbol", "UNKNOWN")
                        )
                    )

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

        if domain == "alpha":
            return {
                "approved": False,
                "reason": "Alpha execution disabled"
            }

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

