"""DEMO trading for Spot (long-only), sharing the Futures lifecycle.

Money moves only inside the internal DEMO ledger; prices are real Binance
Spot order-book data (ask to buy, bid to sell).
"""
import time
from decimal import Decimal, ROUND_DOWN

from core.learning import setup_key as make_setup_key
from core.trailing_stop import calculate_trailing_stop

SPOT_LIKE = ("spot",)
MAX_ENTRY_DEVIATION = Decimal("0.01")
MIN_NOTIONAL = Decimal("10")


class SpotDemoMixin:

    # ---- prices ----------------------------------------------------------------

    def _spot_like_price(self, domain, symbol, side):
        """Reference price for a BUY/SELL, also stored as the account mark."""
        side = side.upper()
        quote = self.market_feed.fetch_book_ticker("spot", symbol)
        mid = Decimal(str(quote["mid_price"]))
        ref = Decimal(str(quote["ask"] if side == "BUY" else quote["bid"]))
        if not ref.is_finite() or ref <= 0 or not mid.is_finite() or mid <= 0:
            raise ValueError("Invalid market price")
        self.demo_execution.update_mark_price(symbol, "SPOT", mid, source="BINANCE")
        return ref

    # ---- scanning ----------------------------------------------------------------

    def scan_spot(self, limit=None, min_quote_volume=None):
        if not self._agent_enabled("spot"):
            return {"success": False, "reason": "Spot agent is stopped",
                    "opportunities": []}
        minimum = float(min_quote_volume) if min_quote_volume is not None else None
        try:
            tickers = self.market_feed._request("spot", "/api/v3/ticker/24hr", {})
            symbols = (self.market_feed.fetch_symbols("spot") if limit is None else
                sorted({str(x.get("symbol", "")).strip().upper() for x in tickers
                        if str(x.get("symbol", "")).strip().upper().endswith("USDT")}))
        except Exception as error:
            cycle_id = self.pipeline_funnel.start("spot", 0)
            self._funnel_record("spot", None, reason=str(error), error=True,
                                fatal=True, cycle_id=cycle_id)
            funnel = self.pipeline_funnel.finish("spot", 0, 0)
            return {"success": False, "reason": "Spot universe scan failed: " + str(error),
                    "opportunities": [], "errors": {"__universe__": str(error)},
                    "error_count": 1, "fatal_errors": 1, "funnel": funnel}
        ticker_by_symbol = {str(x.get("symbol", "")).strip().upper(): x for x in tickers}
        ranked = []
        for symbol in symbols:
            item = ticker_by_symbol.get(symbol, {})
            try:
                volume, price = float(item.get("quoteVolume", 0)), float(item.get("lastPrice", 0))
            except (TypeError, ValueError):
                volume, price = 0.0, 0.0
            if minimum is not None and volume < minimum:
                continue
            ranked.append({"symbol": symbol, "quote_volume": volume, "last_price": price})
        ranked.sort(key=lambda item: item["quote_volume"], reverse=True)
        universe = ranked if limit is None else ranked[:max(1, int(limit))]
        scan_meta = {"universe_total": len(universe), "batch_size": len(universe),
                     "cycle": 0, "cycle_complete": True}
        if limit is None:
            from core.scan_rotation import next_scan_batch
            universe, scan_meta = next_scan_batch("spot", universe, batch_size=20)
        cycle_id = self.pipeline_funnel.start("spot", len(universe), "5m")
        opportunities, errors, rejections, rejection_samples = [], {}, {}, []
        def reject(symbol, reason):
            key = str(reason or "No actionable signal")
            rejections[key] = rejections.get(key, 0) + 1
            self._funnel_record("spot", None, reason=key, cycle_id=cycle_id)
            if len(rejection_samples) < 10:
                rejection_samples.append({"symbol": symbol, "reason": key})
        processed = 0
        for item in universe:
            symbol = item["symbol"]
            self._funnel_record("spot", "events_received", cycle_id=cycle_id)
            try:
                analysis = self.analyze_live(symbol, domains=["spot"])
                signal = analysis.get("signals", {}).get("spot", {})
                if analysis.get("data_errors") or (
                    isinstance(signal, dict) and signal.get("error")
                ):
                    errors[symbol] = str(
                        (signal.get("error") if isinstance(signal, dict) else None)
                        or analysis.get("data_errors"))
                    self._funnel_record("spot", None, error=True,
                                        reason="Analysis data error", cycle_id=cycle_id)
                    continue
                processed += 1
                if not isinstance(signal, dict):
                    reject(symbol, "Missing Spot analysis")
                    continue
                self._funnel_record("spot", "passed_filter", cycle_id=cycle_id)
                if str(signal.get("direction", "")).upper() != "BUY":
                    reject(symbol, signal.get("reason") or "Spot signal is not BUY")
                    continue
                self._funnel_record("spot", "strategy_accepted", cycle_id=cycle_id)
                opp = self._as_opportunity(item, signal, "spot")
                if opp:
                    self._funnel_record("spot", "valid_plan", cycle_id=cycle_id)
                    signal["_funnel_cycle_id"] = cycle_id
                    opp["scan_cycle_id"] = cycle_id
                    opportunities.append(opp)
                else:
                    plan = signal.get("trade_plan") or {}
                    reject(symbol, plan.get("reason") or "Trade plan rejected")
            except Exception as error:
                errors[symbol] = str(error)
                self._funnel_record("spot", None, error=True,
                                    reason="Symbol analysis exception", cycle_id=cycle_id)
        result = self._finish_scan("spot", universe, opportunities, errors,
            rejections=rejections, rejection_samples=rejection_samples,
            cycle_id=cycle_id, processed=processed)
        result["scan"] = scan_meta
        return result

    def _as_opportunity(self, item, signal, domain):
        if not isinstance(signal, dict):
            return None
        if str(signal.get("direction", "")).upper() != "BUY":
            return None
        plan = signal.get("trade_plan")
        if signal.get("strategy_version") != "v3" or not isinstance(plan, dict) or plan.get("strategy_version") != "v3":
            return None
        if plan.get("success") is not True:
            return None
        return {**item, "direction": "LONG", "confidence":
                float(signal.get("confidence", 0) or 0),
                "trade_plan": plan, "signal": signal, "domain": domain}

    def _finish_scan(self, domain, universe, opportunities, errors,
                     rejections=None, rejection_samples=None,
                     cycle_id=None, processed=None):
        opportunities.sort(key=lambda o: (o["confidence"],
                                          o.get("quote_volume", 0)), reverse=True)
        if opportunities:
            self.last_signals[domain] = opportunities[0]["signal"]
        funnel = self.pipeline_funnel.finish(
            domain, processed=processed, expected=len(universe))
        return {"success": bool(funnel["success"]), "scanned": len(universe),
                "actionable": len(opportunities),
                "selected": opportunities[0]["symbol"] if opportunities else None,
                "opportunities": opportunities, "errors": errors,
                "error_count": len(errors), "fatal_errors": funnel["fatal_errors"],
                "rejections": rejections or {},
                "rejection_samples": rejection_samples or [],
                "funnel": funnel}

    # ---- open --------------------------------------------------------------------

    def request_demo_spot_trade(self, symbol, domain="spot", risk_pct=0.5,
                                signal_override=None):
        with self._demo_lock:
            return self._request_demo_spot_trade_locked(
                symbol, domain, risk_pct, signal_override
            )

    def _request_demo_spot_trade_locked(self, symbol, domain, risk_pct,
                                        signal_override=None):
        symbol = str(symbol).strip().upper()
        domain = str(domain).strip().lower()
        if domain not in SPOT_LIKE:
            return {"approved": False, "reason": "Invalid domain"}
        if self.mode != "DEMO" or self.demo_execution is None:
            return {"approved": False, "reason": "Select DEMO mode first"}
        if not self._agent_enabled(domain):
            return {"approved": False, "reason": domain.title() + " agent is stopped"}

        live_statuses = ("DEMO_OPEN", "DEMO_PARTIALLY_CLOSED")
        if any(p.get("status") in ("DEMO_UNPROTECTED", "DEMO_RECONCILIATION_REQUIRED")
               for p in self.demo_positions.values()):
            return {"approved": False, "reason": "An unresolved DEMO position exists"}
        active = [p for p in self.demo_positions.values()
                  if p.get("status") in live_statuses]
        if len(active) >= int(self.max_concurrent_demo):
            return {"approved": False, "reason": "Max concurrent DEMO positions reached"}
        if any(str(p.get("symbol")).upper() == symbol for p in active):
            return {"approved": False, "reason": "A DEMO position on this symbol is already open"}

        # Keep manual chart analysis bound to its own signal even if autopilot
        # refreshes the shared latest-signal cache concurrently.
        signal = signal_override if isinstance(signal_override, dict) else self.last_signals.get(domain, {})
        if str(signal.get("symbol", "")).upper() != symbol:
            return {"approved": False, "reason": "Symbol does not match latest signal"}
        if str(signal.get("direction", "")).upper() != "BUY":
            return {"approved": False, "reason": "Latest signal is not BUY"}
        plan = signal.get("trade_plan")
        if signal.get("strategy_version") != "v3" or not isinstance(plan, dict) or plan.get("success") is not True or plan.get("strategy_version") != "v3":
            return {"approved": False, "reason": "Only an approved V3 Spot trade plan is permitted"}

        trade_id = None
        try:
            entry = Decimal(str(plan["entry"]))
            stop = Decimal(str(plan["stop_loss"]))
            target = Decimal(str(plan["take_profit"]))
            if not all(x.is_finite() and x > 0 for x in (entry, stop, target)):
                raise ValueError("Invalid trade plan prices")
            if not stop < entry < target:
                raise ValueError("Invalid LONG trade plan levels")

            price = self._spot_like_price(domain, symbol, "BUY")
            valid_entry, entry_reason = self._validate_demo_entry_price(
                plan, "LONG", price, min_net_rr=1.5, market="spot",
                signal_created_at=signal.get("_signal_created_at"),
            )
            if not valid_entry:
                return {"approved": False, "reason": entry_reason}
            if not stop < price < target:
                return {"approved": False, "reason": "Price is outside the plan range"}

            reservation = self.risk.reserve_trade(
                domain=domain, symbol=symbol, direction="LONG",
                entry=float(entry), stop_loss=float(stop),
                risk_pct=float(risk_pct), leverage=1)
            if not reservation.get("approved"):
                return reservation
            self._funnel_record("spot", "risk_approved",
                                cycle_id=signal.get("_funnel_cycle_id"))
            trade_id = reservation["trade_id"]
            self.risk.update_reservation_status(trade_id, "DEMO_PENDING")

            quantity = Decimal(str(reservation["quantity"])).quantize(
                Decimal("0.00000001"), rounding=ROUND_DOWN)
            if quantity <= 0 or quantity * price < MIN_NOTIONAL:
                self.risk.release_reservation(trade_id)
                return {"approved": False, "reason": "Order below the minimum notional"}

            execution = self.demo_execution.submit_order(
                self.demo_account_id, agent_id=domain, symbol=symbol,
                market_type="SPOT", side="BUY", quantity=quantity,
                market_price=price)

            opened_at_ms = int(time.time() * 1000)
            record = {
                "position_id": trade_id, "trade_id": trade_id,
                "domain": domain, "symbol": symbol,
                "display_symbol": symbol,
                "direction": "LONG",
                "quantity": str(execution["quantity"]),
                "entry_price": str(execution["execution_price"]),
                "stop_loss": str(stop), "take_profit": str(target),
                "structure_support": str(plan["support"]) if plan.get("support") is not None else None,
                "next_support": str(plan["next_support"]) if plan.get("next_support") is not None else None,
                "structure_resistance": str(plan["resistance"]) if plan.get("resistance") is not None else None,
                "next_resistance": str(plan["next_resistance"]) if plan.get("next_resistance") is not None else None,
                "entry_confirmation": str(plan.get("entry_confirmation") or ""),
                "entry_strategy": str(plan.get("entry_strategy") or ""),
                "net_reward_risk": float(plan.get("net_reward_risk", 0)),
                "max_hold_minutes": int(plan.get("max_hold_minutes", 0) or 0),
                "entry_fee": str(execution["fee"]),
                "total_fees": str(execution["fee"]),
                "status": "DEMO_OPEN",
                "execution_source": "INTERNAL_DEMO",
                "protection_verified": False,
                "opened_at_ms": opened_at_ms,
                **self._entry_chart_metadata(signal, opened_at_ms),
                "last_checked_ms": int(time.time() * 1000),
                "leverage": "1",
            }
            self.demo_positions[trade_id] = record
            self._on_demo_open(record, signal, reservation)
            self._save_demo_state()
            self.risk.update_reservation_status(
                trade_id, "DEMO_OPEN", protection_verified=False,
                execution_source="INTERNAL_DEMO")
            self._funnel_record("spot", "trade_opened",
                                cycle_id=signal.get("_funnel_cycle_id"))
            return {"approved": True, "mode": "DEMO", **record}

        except Exception as error:
            if trade_id and "Insufficient DEMO cash" in str(error):
                self.risk.release_reservation(trade_id)
                return {"approved": False, "mode": "DEMO", "reason": str(error)}
            if trade_id:
                self.risk.update_reservation_status(
                    trade_id, "DEMO_UNPROTECTED", execution_error=str(error))
                self.demo_positions[trade_id] = {
                    "position_id": trade_id, "trade_id": trade_id,
                    "domain": domain, "symbol": symbol, "direction": "LONG",
                    "status": "DEMO_UNPROTECTED", "error": str(error),
                    "execution_source": "INTERNAL_DEMO"}
                self._save_demo_state()
            return {"approved": False, "mode": "DEMO", "reason": str(error)}

    # ---- close / monitor ----------------------------------------------------------

    def _close_spot_like(self, position_id, record, reason, exit_price=None):
        domain, symbol = record["domain"], str(record["symbol"]).upper()
        quantity = Decimal(str(record["quantity"]))
        price = (Decimal(str(exit_price)) if exit_price is not None
                 else self._spot_like_price(domain, symbol, "SELL"))
        result = self.demo_execution.submit_order(
            self.demo_account_id, agent_id=domain, symbol=symbol,
            market_type="SPOT", side="SELL", quantity=quantity,
            market_price=price)

        fee = Decimal(str(result["fee"]))
        realized = Decimal(str(result["realized_pnl"]))      # already net of the sell fee
        record["status"] = "DEMO_CLOSED"
        record["close_reason"] = reason
        record["close_price"] = str(result["execution_price"])
        record["close_fee"] = str(fee)
        record["remaining_quantity"] = "0"
        # engine realized PnL includes the sell fee; _apply_close_result expects gross
        self._apply_close_result(record, {"realized_pnl": realized + fee, "fee": fee})
        record["realized_pnl"] = str(realized + fee)
        settled = self._settle_risk(position_id, record, reason)
        record["risk_settled"] = bool(settled.get("success"))
        self._save_demo_state()
        return result

    def _monitor_spot_like(self):
        events = []
        with self._demo_lock:
            position_ids = [
                str(position_id) for position_id, record in self.demo_positions.items()
                if record.get("domain") in SPOT_LIKE
                and record.get("status") in ("DEMO_OPEN", "DEMO_PARTIALLY_CLOSED")
            ]

        for position_id in position_ids:
            with self._demo_position_lock(position_id):
                with self._demo_lock:
                    record = self.demo_positions.get(position_id)
                    if (
                        not record
                        or record.get("domain") not in SPOT_LIKE
                        or record.get("status") not in ("DEMO_OPEN", "DEMO_PARTIALLY_CLOSED")
                    ):
                        continue
                    snapshot = dict(record)

                try:
                    domain = snapshot["domain"]
                    symbol = str(snapshot["symbol"]).upper()
                    stop = Decimal(str(snapshot["stop_loss"]))
                    target = Decimal(str(snapshot["take_profit"]))
                    trailing_active = bool(snapshot.get("trailing_stop_active"))

                    # Quote and candle catch-up run without the global coordinator lock.
                    price = self._spot_like_price(domain, symbol, "SELL")
                    trail_update = None
                    if trailing_active:
                        try:
                            trail_frame = self.market_feed.fetch_candles(
                                "spot", symbol, "5m", limit=40, closed_only=True)
                            trail_update = calculate_trailing_stop(
                                trail_frame, "LONG", stop,
                                snapshot.get("trailing_best_price"), price)
                            if trail_update:
                                stop = Decimal(str(trail_update["stop"]))
                        except Exception as trail_error:
                            with self._demo_lock:
                                current = self.demo_positions.get(position_id)
                                if current:
                                    current["trailing_update_error"] = str(trail_error)
                    try:
                        missed = self._catch_up(
                            snapshot, "LONG", stop,
                            None if trailing_active else target)
                    except Exception as catch_error:
                        missed = None
                        with self._demo_lock:
                            current = self.demo_positions.get(position_id)
                            if current:
                                current["catch_up_error"] = str(catch_error)

                    reason, exit_price = (missed if missed else (None, price))
                    if reason is None:
                        if price <= stop:
                            reason = "TRAILING_STOP" if trailing_active else "STOP_LOSS"
                        elif not trailing_active and price >= target:
                            reason = "TAKE_PROFIT"
                    max_hold = int(snapshot.get("max_hold_minutes") or 0)
                    opened_ms = int(snapshot.get("opened_at_ms") or 0)
                    if reason is None and max_hold > 0 and opened_ms > 0:
                        if int(time.time() * 1000) - opened_ms >= max_hold * 60_000:
                            reason = "TIME_EXIT"
                    with self._demo_lock:
                        current = self.demo_positions.get(position_id)
                        if not current or current.get("status") not in (
                            "DEMO_OPEN", "DEMO_PARTIALLY_CLOSED"
                        ):
                            continue
                        current["last_checked_ms"] = int(time.time() * 1000)
                        if trailing_active:
                            current["trailing_stop_active"] = True
                            current["trailing_best_price"] = str(
                                trail_update["best_price"] if trail_update
                                else snapshot.get("trailing_best_price") or price)
                            current["stop_loss"] = str(
                                trail_update["stop"] if trail_update else stop)
                            current["trailing_activated_ms"] = (
                                current.get("trailing_activated_ms")
                                or int(time.time() * 1000))
                            current["trailing_stop_method"] = (
                                trail_update.get("method", "ATR_1.5x_PLUS_5_CANDLE_STRUCTURE")
                                if trail_update else "ATR_1.5x_PLUS_5_CANDLE_STRUCTURE")
                            if trail_update and trail_update.get("atr") is not None:
                                current["trailing_atr"] = str(trail_update["atr"])
                                current["trailing_structure_level"] = str(
                                    trail_update["structure_level"])
                        if reason:
                            result = self._close_spot_like(
                                position_id, current, reason, exit_price
                            )
                            events.append({
                                "position_id": position_id, "symbol": symbol,
                                "reason": reason, "result": result,
                            })
                        else:
                            self._save_demo_state()
                except Exception as error:
                    events.append({
                        "position_id": position_id,
                        "symbol": snapshot.get("symbol"),
                        "error": str(error),
                    })
        return events
