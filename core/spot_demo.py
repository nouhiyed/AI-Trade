"""DEMO trading for Spot and Alpha (long-only), same lifecycle as Futures.

Mixed into TradingCoordinator. Money moves only inside the internal DEMO
ledger; prices are real Binance data. Spot uses the real order book (ask to
buy, bid to sell). Alpha uses the token price with extra slippage.
"""
import os
import time
from decimal import Decimal, ROUND_DOWN

from core.learning import setup_key as make_setup_key

SPOT_LIKE = ("spot", "alpha")
MAX_ENTRY_DEVIATION = Decimal("0.01")
MIN_NOTIONAL = Decimal("10")


class SpotDemoMixin:

    # ---- prices ----------------------------------------------------------------

    def _spot_like_price(self, domain, symbol, side):
        """Reference price for a BUY/SELL, also stored as the account mark."""
        side = side.upper()
        if domain == "spot":
            quote = self.market_feed.fetch_book_ticker("spot", symbol)
            mid = Decimal(str(quote["mid_price"]))
            ref = Decimal(str(quote["ask"] if side == "BUY" else quote["bid"]))
        else:
            mid = Decimal(str(self.alpha_feed.price(symbol)))
            slip = Decimal(str(self.alpha_feed.EXTRA_SLIPPAGE))
            ref = mid * (1 + slip) if side == "BUY" else mid * (1 - slip)
        if not ref.is_finite() or ref <= 0 or not mid.is_finite() or mid <= 0:
            raise ValueError("Invalid market price")
        self.demo_execution.update_mark_price(symbol, "SPOT", mid, source="BINANCE")
        return ref

    # ---- scanning ----------------------------------------------------------------

    def scan_spot(self, limit=8, min_quote_volume=None):
        if not self._agent_enabled("spot"):
            return {"success": False, "reason": "Spot agent is stopped",
                    "opportunities": []}
        minimum = float(min_quote_volume if min_quote_volume is not None
                        else os.getenv("SPOT_MIN_QUOTE_VOLUME", "20000000"))
        try:
            tickers = self.market_feed._request("spot", "/api/v3/ticker/24hr", {})
        except Exception as error:
            return {"success": False,
                    "reason": "Spot universe scan failed: " + str(error),
                    "opportunities": []}
        skip = ("UPUSDT", "DOWNUSDT", "USDCUSDT", "FDUSDUSDT", "TUSDUSDT",
                "BUSDUSDT", "USDPUSDT", "EURUSDT", "AEURUSDT", "USD1USDT", "DAIUSDT")
        ranked = []
        for item in tickers:
            symbol = str(item.get("symbol", ""))
            if not symbol.endswith("USDT") or symbol.endswith(skip) or "_" in symbol:
                continue
            try:
                volume = float(item.get("quoteVolume", 0))
                price = float(item.get("lastPrice", 0))
            except (TypeError, ValueError):
                continue
            if volume >= minimum and price > 0:
                ranked.append({"symbol": symbol, "quote_volume": volume,
                               "last_price": price})
        ranked.sort(key=lambda r: r["quote_volume"], reverse=True)
        universe = ranked[: max(1, min(int(limit), 30))]

        opportunities, errors = [], {}
        rejections, rejection_samples = {}, []

        def reject(symbol, reason):
            reason = str(reason or "No actionable signal")
            rejections[reason] = rejections.get(reason, 0) + 1
            if len(rejection_samples) < 10:
                rejection_samples.append({"symbol": symbol, "reason": reason})

        for item in universe:
            symbol = item["symbol"]
            try:
                analysis = self.analyze_live(symbol)
                signal = analysis.get("signals", {}).get("spot", {})
                opp = self._as_opportunity(item, signal, "spot")
                if opp:
                    opportunities.append(opp)
                elif not isinstance(signal, dict):
                    reject(symbol, "Missing Spot analysis")
                elif str(signal.get("direction", "")).upper() != "BUY":
                    reject(symbol, signal.get("reason") or "Spot signal is not BUY")
                else:
                    plan = signal.get("trade_plan") or {}
                    reject(symbol, plan.get("reason") or "Trade plan rejected")
            except Exception as error:
                errors[symbol] = str(error)
        return self._finish_scan(
            "spot", universe, opportunities, errors,
            rejections=rejections, rejection_samples=rejection_samples)

    def _as_opportunity(self, item, signal, domain):
        if not isinstance(signal, dict):
            return None
        if str(signal.get("direction", "")).upper() != "BUY":
            return None
        if domain == "alpha":
            safety = signal.get("token_safety") or {}
            if str(safety.get("status", "")).upper() != "PASS":
                return None
        plan = signal.get("trade_plan")
        if not isinstance(plan, dict) or plan.get("success") is not True:
            return None
        return {**item, "direction": "LONG", "confidence":
                float(signal.get("confidence", 0) or 0),
                "trade_plan": plan, "signal": signal, "domain": domain}

    def _finish_scan(self, domain, universe, opportunities, errors,
                     rejections=None, rejection_samples=None):
        opportunities.sort(key=lambda o: (o["confidence"],
                                          o.get("quote_volume", 0)), reverse=True)
        if opportunities:
            self.last_signals[domain] = opportunities[0]["signal"]
        return {"success": True, "scanned": len(universe),
                "actionable": len(opportunities),
                "selected": opportunities[0]["symbol"] if opportunities else None,
                "opportunities": opportunities, "errors": errors,
                "rejections": rejections or {},
                "rejection_samples": rejection_samples or []}

    def _alpha_safety(self, token):
        """Auto token-safety from the contract data of the Alpha token list."""
        cache = getattr(self, "_alpha_safety_cache", None)
        if cache is None:
            cache = self._alpha_safety_cache = {}
        key = token["symbol"]
        hit = cache.get(key)
        if hit and time.time() - hit[0] < 3600:
            return hit[1]
        unknown = {"status": "UNKNOWN", "passed": False, "critical": False}
        if not token.get("chain_id") or not token.get("address"):
            result = unknown
        else:
            try:
                result = self.safety_engine.check_token(
                    token["chain_id"], token["address"])
                if not isinstance(result, dict):
                    result = unknown
            except Exception:
                result = unknown
        cache[key] = (time.time(), result)
        return result

    def analyze_alpha(self, token, preferred_timeframe=None):
        """Run the Alpha agent on real Alpha candles with automatic safety."""
        symbol = token["symbol"]
        live = {"symbol": symbol, "timeframes": {"alpha": {}},
                "orderbooks": {"alpha": {}}, "errors": {}}
        for tf in self.market_engine.timeframes["alpha"]:
            df = self.market_feed.fetch_alpha_candles(symbol, tf, limit=300)
            live["timeframes"]["alpha"][tf] = self.market_engine._prepare_frame(
                df, symbol, "alpha", tf)
        data = self.market_engine.for_live_agent(live, "alpha")
        data["token_safety"] = self._alpha_safety(token)
        signal = self.agents["alpha"].analyze(data)
        if isinstance(signal, dict) and str(signal.get("direction")).upper() == "BUY":
            signal["trade_plan"] = self.trade_planner.create(
                data, "LONG", preferred_timeframe=preferred_timeframe
            )
        return signal

    def scan_alpha(self, limit=6):
        if not self._agent_enabled("alpha"):
            return {"success": False, "reason": "Alpha agent is stopped",
                    "opportunities": []}
        try:
            universe = self.alpha_feed.universe(limit=limit)
        except Exception as error:
            return {"success": False,
                    "reason": "Alpha universe scan failed: " + str(error),
                    "opportunities": []}
        opportunities, errors = [], {}
        rejections, rejection_samples = {}, []

        def reject(symbol, reason):
            reason = str(reason or "No actionable signal")
            rejections[reason] = rejections.get(reason, 0) + 1
            if len(rejection_samples) < 10:
                rejection_samples.append({"symbol": symbol, "reason": reason})

        for token in universe:
            try:
                signal = self.analyze_alpha(token)
                item = {"symbol": token["symbol"], "display": token["display"],
                        "quote_volume": token["volume_24h"],
                        "liquidity": token["liquidity"]}
                opp = self._as_opportunity(item, signal, "alpha")
                if opp:
                    opportunities.append(opp)
                elif str((signal.get("token_safety") or {}).get("status", "")).upper() != "PASS":
                    reject(token["symbol"], "Token safety is not PASS")
                elif str(signal.get("direction", "")).upper() != "BUY":
                    reject(token["symbol"], signal.get("reason") or "Alpha signal is not BUY")
                else:
                    plan = signal.get("trade_plan") or {}
                    reject(token["symbol"], plan.get("reason") or "Trade plan rejected")
            except Exception as error:
                errors[token["symbol"]] = str(error)
        return self._finish_scan(
            "alpha", universe, opportunities, errors,
            rejections=rejections, rejection_samples=rejection_samples)

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
        if domain == "alpha":
            status = str((signal.get("token_safety") or {}).get("status", "")).upper()
            if status != "PASS":
                return {"approved": False, "reason": "Alpha token safety is not PASS"}
        plan = signal.get("trade_plan")
        if not isinstance(plan, dict) or plan.get("success") is not True:
            return {"approved": False, "reason": "No approved trade plan"}

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
            if abs(price - entry) / entry > MAX_ENTRY_DEVIATION:
                return {"approved": False, "reason": "Price moved away from the plan entry"}
            if not stop < price < target:
                return {"approved": False, "reason": "Price is outside the plan range"}

            reservation = self.risk.reserve_trade(
                domain=domain, symbol=symbol, direction="LONG",
                entry=float(entry), stop_loss=float(stop),
                risk_pct=float(risk_pct), leverage=1)
            if not reservation.get("approved"):
                return reservation
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

            token = {}
            if domain == "alpha":
                try:
                    token = self.alpha_feed.token(symbol)
                except Exception:
                    token = {}
            record = {
                "position_id": trade_id, "trade_id": trade_id,
                "domain": domain, "symbol": symbol,
                "display_symbol": token.get("display") or symbol,
                "direction": "LONG",
                "quantity": str(execution["quantity"]),
                "entry_price": str(execution["execution_price"]),
                "stop_loss": str(stop), "take_profit": str(target),
                "entry_fee": str(execution["fee"]),
                "total_fees": str(execution["fee"]),
                "status": "DEMO_OPEN",
                "execution_source": "INTERNAL_DEMO",
                "protection_verified": False,
                "opened_at_ms": int(time.time() * 1000),
                "last_checked_ms": int(time.time() * 1000),
                "leverage": "1",
            }
            self.demo_positions[trade_id] = record
            self._on_demo_open(record, signal, reservation)
            self._save_demo_state()
            self.risk.update_reservation_status(
                trade_id, "DEMO_OPEN", protection_verified=False,
                execution_source="INTERNAL_DEMO")
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

                    # Quote and candle catch-up run without the global coordinator lock.
                    price = self._spot_like_price(domain, symbol, "SELL")
                    try:
                        missed = self._catch_up(snapshot, "LONG", stop, target)
                    except Exception as catch_error:
                        missed = None
                        with self._demo_lock:
                            current = self.demo_positions.get(position_id)
                            if current:
                                current["catch_up_error"] = str(catch_error)

                    reason, exit_price = (missed if missed else (None, price))
                    if reason is None:
                        if price <= stop:
                            reason = "STOP_LOSS"
                        elif price >= target:
                            reason = "TAKE_PROFIT"

                    with self._demo_lock:
                        current = self.demo_positions.get(position_id)
                        if not current or current.get("status") not in (
                            "DEMO_OPEN", "DEMO_PARTIALLY_CLOSED"
                        ):
                            continue
                        current["last_checked_ms"] = int(time.time() * 1000)
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
