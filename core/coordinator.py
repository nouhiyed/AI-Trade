
import json
from pathlib import Path

from agents.futures.agent import FuturesAgent
from agents.spot.agent import SpotAgent
from agents.alpha.agent import AlphaAgent

from core.risk_manager import RiskManager
from core.market_data_engine import MarketDataEngine
from core.token_safety_engine import TokenSafetyEngine
from core.paper_trading_engine import PaperTradingEngine
from core.binance_market_data import BinanceMarketData
from core.market_scanner import FuturesMarketScanner
from core.trade_planner import TradePlanner
from core.binance_execution import BinanceExecutionEngine


class TradingCoordinator:

    def __init__(self, initial_balance=1000):
        self.risk = RiskManager(initial_balance=initial_balance)
        self.paper = PaperTradingEngine(initial_balance=initial_balance)
        self.paper_price_feed = BinanceMarketData(timeout=6)
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
        self.alpha_config_path = Path("config/alpha_tokens.json")
        self.mode = "PAPER"
        self.demo_execution = None
        self.demo_state_path = Path("config/demo_state.json")
        self.demo_positions = self._load_demo_state()


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

    def set_mode(self, mode):
        mode = str(mode).strip().upper()
        if mode == "LIVE":
            return {"success": False, "reason": "LIVE is not enabled"}
        if mode not in ("PAPER", "DEMO"):
            return {"success": False, "reason": "Unsupported mode"}
        if mode == "DEMO":
            if any(
                p.get("status") in ("DEMO_OPEN", "DEMO_UNPROTECTED",
                                    "DEMO_RECONCILIATION_REQUIRED")
                for p in self.demo_positions.values()
            ):
                return {
                    "success": False,
                    "reason": "Resolve existing DEMO positions before changing mode"
                }
            try:
                if self.demo_execution is None:
                    self.demo_execution = BinanceExecutionEngine(mode="DEMO")
            except Exception as error:
                return {"success": False, "reason": str(error)}
        self.mode = mode
        return {"success": True, "mode": self.mode}

    def get_demo_positions(self):
        return {
            "mode": self.mode,
            "positions": list(self.demo_positions.values())
        }


    def close_demo_position(self, position_id):
        position_id = str(position_id).strip()
        record = self.demo_positions.get(position_id)

        if not record:
            return {"success": False, "reason": "DEMO position not found"}
        if record.get("status") not in (
            "DEMO_OPEN", "DEMO_UNPROTECTED",
            "DEMO_RECONCILIATION_REQUIRED"
        ):
            return {"success": False, "reason": "Position is not closable"}

        engine = self.demo_execution
        if engine is None:
            try:
                engine = BinanceExecutionEngine(mode="DEMO")
                self.demo_execution = engine
            except Exception as error:
                return {"success": False, "reason": str(error)}

        symbol = str(record["symbol"]).upper()
        direction = str(record["direction"]).upper()

        try:
            positions = engine.get_futures_positions(symbol)
            matching = []
            for item in positions:
                if str(item.get("symbol", "")).upper() != symbol:
                    continue
                amount = Decimal(str(item.get("positionAmt", "0")))
                if amount == 0:
                    continue
                side = str(item.get("positionSide", "BOTH")).upper()
                if side == direction or (
                    side == "BOTH" and
                    ((direction == "LONG" and amount > 0) or
                     (direction == "SHORT" and amount < 0))
                ):
                    matching.append((item, amount))

            if len(matching) > 1:
                raise RuntimeError("Ambiguous exchange position; manual reconciliation required")

            if matching:
                item, amount = matching[0]
                quantity = format(abs(amount), "f")
                hedge = str(item.get("positionSide", "BOTH")).upper() != "BOTH"
                side = "SELL" if direction == "LONG" else "BUY"

                order = engine.place_market_order(
                    market="futures",
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    reduce_only=not hedge,
                    position_side=direction if hedge else None
                )

                if not isinstance(order, dict):
                    raise RuntimeError("Invalid close order response")

                if order.get("status") != "FILLED":
                    order_id = order.get("orderId")
                    if not order_id:
                        raise RuntimeError("Close order is not confirmed FILLED")
                    order = engine.get_order("futures", symbol, order_id)

                if not isinstance(order, dict) or order.get("status") != "FILLED":
                    raise RuntimeError("Binance did not confirm the close")

            # Verify the exact position side is gone before cancelling protection.
            remaining = engine.get_futures_positions(symbol)
            still_open = False
            for item in remaining:
                if str(item.get("symbol", "")).upper() != symbol:
                    continue
                amount = Decimal(str(item.get("positionAmt", "0")))
                if amount == 0:
                    continue
                side = str(item.get("positionSide", "BOTH")).upper()
                if side == direction or (
                    side == "BOTH" and
                    ((direction == "LONG" and amount > 0) or
                     (direction == "SHORT" and amount < 0))
                ):
                    still_open = True
                    break

            if still_open:
                record["status"] = "DEMO_RECONCILIATION_REQUIRED"
                record["close_error"] = "Exchange position remains after close"
                self._save_demo_state()
                self.risk.update_reservation_status(
                    position_id, "DEMO_RECONCILIATION_REQUIRED",
                    close_verified=False
                )
                return {"success": False, "reason": record["close_error"]}

            # Cancel only this position's known protection IDs, after verified closure.
            cancel_errors = []
            for key in ("stop_algo_id", "target_algo_id"):
                algo_id = record.get(key)
                if algo_id:
                    try:
                        engine.cancel_futures_algo_order(symbol, algo_id)
                    except Exception as error:
                        cancel_errors.append(str(error))

            record["status"] = "DEMO_CLOSED_PENDING_RECONCILIATION"
            record["close_verified"] = True
            record["protection_cancel_errors"] = cancel_errors
            self._save_demo_state()

            self.risk.update_reservation_status(
                position_id, "DEMO_RECONCILIATION_REQUIRED",
                close_verified=True,
                settlement_pending=True
            )

            return {
                "success": True,
                "position_id": position_id,
                "exchange_closed": True,
                "settlement": "PENDING_REALIZED_PNL_VERIFICATION",
                "protection_cancel_errors": cancel_errors
            }

        except Exception as error:
            record["status"] = "DEMO_RECONCILIATION_REQUIRED"
            record["close_error"] = str(error)
            self._save_demo_state()
            self.risk.update_reservation_status(
                position_id, "DEMO_RECONCILIATION_REQUIRED",
                close_error=str(error)
            )
            return {"success": False, "reason": str(error)}

    def request_demo_futures_trade(
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

        if any(
            p.get("status") in ("DEMO_OPEN", "DEMO_UNPROTECTED",
                                "DEMO_RECONCILIATION_REQUIRED")
            for p in self.demo_positions.values()
        ):
            return {"approved": False, "reason": "An unresolved DEMO position exists"}

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

        try:
            from decimal import Decimal
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
                domain="futures", symbol=symbol, direction=direction,
                entry=float(entry), stop_loss=float(stop),
                risk_pct=float(risk_pct), leverage=int(leverage)
            )
            if not reservation.get("approved"):
                return reservation

            trade_id = reservation["trade_id"]
            self.risk.update_reservation_status(trade_id, "DEMO_PENDING")

            engine = self.demo_execution
            filters = engine.get_futures_symbol_filters(symbol)
            quantity = engine.round_futures_quantity(
                reservation["quantity"], filters
            )
            qty_dec = Decimal(quantity)
            min_notional = filters.get("min_notional")
            if min_notional is not None:
                if qty_dec * entry < Decimal(str(min_notional)):
                    raise ValueError("Order is below Binance minimum notional")

            rounded_stop = engine.round_futures_price(stop, filters)
            rounded_target = engine.round_futures_price(target, filters)

            engine.set_futures_leverage(symbol, int(leverage))
            position_mode = engine.get_futures_position_mode()
            hedge = bool(position_mode.get("dualSidePosition"))
            position_side = direction if hedge else None
            side = "BUY" if direction == "LONG" else "SELL"

            order = engine.place_market_order(
                market="futures", symbol=symbol, side=side,
                quantity=quantity, position_side=position_side
            )
            if not isinstance(order, dict):
                raise RuntimeError("Invalid Binance entry response")

            if order.get("status") != "FILLED":
                order_id = order.get("orderId")
                if not order_id:
                    raise RuntimeError("Entry order is not confirmed FILLED")
                order = engine.get_order("futures", symbol, order_id)

            if not isinstance(order, dict) or order.get("status") != "FILLED":
                raise RuntimeError("Binance did not confirm a filled entry")

            executed = Decimal(str(order.get("executedQty", "0")))
            avg_price = Decimal(str(order.get("avgPrice", "0")))
            if executed <= 0 or avg_price <= 0:
                raise RuntimeError("Invalid confirmed execution quantity or price")

            protection = engine.place_futures_protection(
                symbol=symbol,
                direction=direction,
                stop_loss=rounded_stop,
                take_profit=rounded_target,
                position_side=position_side
            )
            if not protection.get("verified"):
                raise RuntimeError("Protective orders were not verified")

            record = {
                "position_id": trade_id,
                "trade_id": trade_id,
                "domain": "futures",
                "symbol": symbol,
                "direction": direction,
                "quantity": format(executed, "f"),
                "entry_price": format(avg_price, "f"),
                "stop_loss": rounded_stop,
                "take_profit": rounded_target,
                "entry_order_id": order.get("orderId"),
                "stop_algo_id": protection["stop_loss"].get("algoId"),
                "target_algo_id": protection["take_profit"].get("algoId"),
                "status": "DEMO_OPEN",
                "protection_verified": True
            }
            self.demo_positions[trade_id] = record
            self._save_demo_state()
            self.risk.update_reservation_status(
                trade_id, "DEMO_OPEN",
                exchange_order_id=order.get("orderId"),
                protection_verified=True
            )
            return {"approved": True, "mode": "DEMO", **record}

        except Exception as error:
            if "trade_id" in locals():
                self.risk.update_reservation_status(
                    trade_id, "DEMO_UNPROTECTED",
                    execution_error=str(error)
                )
                self.demo_positions[trade_id] = {
                    "position_id": trade_id,
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "direction": direction,
                    "status": "DEMO_UNPROTECTED",
                    "error": str(error),
                    "protection_verified": False
                }
                self._save_demo_state()
            return {"approved": False, "mode": "DEMO", "reason": str(error)}

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


    def analyze_live(self, symbol):
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
                            agent_data, direction
                        )

                if domain == "alpha" and isinstance(signal, dict):
                    signal["execution_enabled"] = False

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

        for item in universe:
            symbol = item["symbol"]
            try:
                analysis = self.analyze_live(symbol)
                signal = analysis.get("signals", {}).get("futures", {})
                if not isinstance(signal, dict):
                    continue

                direction = str(signal.get("direction", "WAIT")).upper()
                confidence = float(signal.get("confidence", 0) or 0)

                if direction not in ("LONG", "SHORT"):
                    continue

                trade_plan = signal.get("trade_plan")
                if not isinstance(trade_plan, dict):
                    continue
                if trade_plan.get("success") is not True:
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

    def request_paper_trade(
        self, domain, symbol, direction, entry, quantity,
        leverage=1, stop_loss=None, take_profit=None
    ):
        domain = str(domain).strip().lower()
        symbol = str(symbol).strip().upper()
        direction = str(direction).strip().upper()

        if domain not in self.agents:
            return {"approved": False, "reason": "Unknown agent"}
        if not self._agent_enabled(domain):
            return {"approved": False, "reason": "Agent is stopped"}

        signal = self.last_signals.get(domain, {})
        if signal.get("symbol") != symbol:
            return {"approved": False, "reason": "Symbol does not match latest signal"}

        if signal.get("direction") != direction:
            return {"approved": False, "reason": "Direction does not match latest signal"}

        if domain == "futures":
            from math import isfinite

            plan = signal.get("trade_plan")
            if not isinstance(plan, dict) or plan.get("success") is not True:
                return {"approved": False, "reason": "No approved Futures trade plan"}

            if str(plan.get("direction", "")).upper() != direction:
                return {"approved": False, "reason": "Trade plan direction mismatch"}

            try:
                plan_entry = float(plan["entry"])
                plan_stop = float(plan["stop_loss"])
                plan_target = float(plan["take_profit"])
            except (KeyError, TypeError, ValueError):
                return {"approved": False, "reason": "Invalid Futures trade plan levels"}

            if not all(isfinite(v) and v > 0 for v in (
                plan_entry, plan_stop, plan_target
            )):
                return {"approved": False, "reason": "Non-finite Futures trade plan levels"}

            if direction == "LONG":
                valid_levels = plan_stop < plan_entry < plan_target
                reward_risk = (
                    (plan_target - plan_entry) / (plan_entry - plan_stop)
                    if valid_levels else 0
                )
            else:
                valid_levels = plan_target < plan_entry < plan_stop
                reward_risk = (
                    (plan_entry - plan_target) / (plan_stop - plan_entry)
                    if valid_levels else 0
                )

            if not valid_levels or reward_risk < 1.5:
                return {"approved": False, "reason": "Futures plan levels or reward/risk rejected"}

            # Futures PAPER entries must use the approved plan levels.
            entry = plan_entry
            stop_loss = plan_stop
            take_profit = plan_target

        if domain in ("spot", "alpha") and direction != "BUY":
            return {"approved": False, "reason": "Spot and Alpha only support BUY entries"}

        if domain == "futures" and direction not in ("LONG", "SHORT"):
            return {"approved": False, "reason": "Futures requires LONG or SHORT"}

        if domain == "alpha":
            safety = self._get_alpha_safety(symbol)
            if str(safety.get("status", "")).upper() != "PASS":
                return {"approved": False, "reason": "Alpha token safety is not PASS"}

        execution_direction = "BUY" if direction == "BUY" else direction

        try:
            result = self.paper.open_position(
                domain=domain,
                symbol=symbol,
                direction=execution_direction,
                price=entry,
                quantity=quantity,
                leverage=leverage,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )
        except Exception as error:
            return {"approved": False, "reason": str(error)}

        return {
            "approved": bool(result.get("success")),
            "mode": "PAPER",
            **result,
        }

    def close_paper_trade(self, position_id, exit_price, quantity=None, reason='MANUAL'):
        try:
            result = self.paper.close_position(
                position_id=position_id,
                price=exit_price,
                quantity=quantity,
                reason=reason,
            )
        except Exception as error:
            return {"success": False, "reason": str(error)}

        if result.get("success") and result.get("remaining_quantity") == "0":
            trade = result.get("trade", {})
            domain = trade.get("domain")
            pnl = float(result.get("realized_pnl", 0))

            if domain in self.agents:
                self.agents[domain].record_trade({
                    "trade_id": position_id,
                    "result": (
                        "WIN" if pnl > 0
                        else "LOSS" if pnl < 0
                        else "BREAKEVEN"
                    ),
                    "realized_pnl": pnl,
                })

        return result

    def close_paper_position_at_market(self, position_id, quantity=None):
        """Close one open PAPER position using a fresh Binance bid/ask quote."""
        position_id = str(position_id).strip()
        if not position_id:
            return {"success": False, "reason": "Missing position_id"}

        positions = self.paper.get_status().get("open_positions", [])
        position = next(
            (item for item in positions if str(item.get("id")) == position_id),
            None,
        )
        if position is None:
            return {"success": False, "reason": "Position not found or already closed"}

        try:
            domain = str(position["domain"]).lower()
            symbol = str(position["symbol"]).upper()
            direction = str(position["direction"]).upper()

            market = "spot" if domain in ("spot", "alpha") else "futures"
            quote = self.paper_price_feed.fetch_book_ticker(market, symbol)

            # A BUY/LONG exits at bid; a SHORT exits at ask.
            exit_price = quote["ask"] if direction == "SHORT" else quote["bid"]
            if not isinstance(exit_price, (int, float)) or exit_price <= 0:
                return {"success": False, "reason": "Invalid market exit quote"}

            result = self.close_paper_trade(
                position_id=position_id,
                exit_price=exit_price,
                quantity=quantity,
                reason="MANUAL",
            )
            if result.get("success"):
                result["exit_quote"] = {
                    "market": market,
                    "symbol": symbol,
                    "bid": quote["bid"],
                    "ask": quote["ask"],
                    "selected_price": exit_price,
                }
            return result
        except Exception as error:
            return {"success": False, "reason": str(error)}

    def monitor_paper_positions(self):
        """Check open PAPER positions against Binance bid/ask prices."""
        positions = self.paper.get_status().get("open_positions", [])
        results = []
        price_cache = {}

        for position in positions:
            try:
                domain = str(position["domain"]).lower()
                symbol = str(position["symbol"]).upper()
                direction = str(position["direction"]).upper()

                market = "spot" if domain in ("spot", "alpha") else "futures"
                cache_key = (market, symbol)

                if cache_key not in price_cache:
                    price_cache[cache_key] = (
                        self.paper_price_feed.fetch_book_ticker(market, symbol)
                    )

                quote = price_cache[cache_key]

                # Exit a long/spot BUY at bid; exit a futures SHORT at ask.
                exit_price = (
                    quote["ask"] if direction == "SHORT" else quote["bid"]
                )

                stop = position.get("stop_loss")
                target = position.get("take_profit")
                if stop is None and target is None:
                    continue

                stop = float(stop) if stop is not None else None
                target = float(target) if target is not None else None

                reason = None
                if direction in ("BUY", "LONG"):
                    if stop is not None and exit_price <= stop:
                        reason = "STOP_LOSS"
                    elif target is not None and exit_price >= target:
                        reason = "TAKE_PROFIT"
                elif direction == "SHORT":
                    if stop is not None and exit_price >= stop:
                        reason = "STOP_LOSS"
                    elif target is not None and exit_price <= target:
                        reason = "TAKE_PROFIT"

                if reason:
                    result = self.close_paper_trade(
                        position_id=position["id"],
                        exit_price=exit_price,
                        reason=reason,
                    )
                    if result.get("success"):
                        results.append({
                            "position_id": position["id"],
                            "symbol": symbol,
                            "reason": reason,
                            "result": result,
                        })
                    else:
                        results.append({
                            "position_id": position["id"],
                            "symbol": symbol,
                            "close_failed": True,
                            "error": result.get("reason", "Close operation failed"),
                        })

            except Exception as error:
                results.append({
                    "position_id": position.get("id"),
                    "symbol": position.get("symbol"),
                    "error": str(error),
                })

        return {
            "checked": len(positions),
            "events": results,
        }

    def get_paper_status(self):
        return self.paper.get_status()

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
            "paper": self.paper.get_status(),
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

