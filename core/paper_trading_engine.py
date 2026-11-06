import json
import os
import threading
import uuid
from decimal import Decimal
from pathlib import Path


class PaperTradingEngine:
    """Persistent paper execution engine. Never sends exchange orders."""

    DOMAINS = {"spot", "alpha", "futures"}

    def __init__(
        self,
        initial_balance=1000,
        state_path="config/paper_state.json",
        fee_rate="0.001",
        slippage_rate="0.0005",
    ):
        self.path = Path(state_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.fee_rate = self._d(fee_rate)
        self.slippage_rate = self._d(slippage_rate)
        self.initial_balance = self._d(initial_balance)

        if self.initial_balance <= 0:
            raise ValueError("Initial balance must be positive")
        if not 0 <= self.fee_rate < 1:
            raise ValueError("Invalid fee rate")
        if not 0 <= self.slippage_rate < 1:
            raise ValueError("Invalid slippage rate")

        if self.path.exists():
            self.state = self._load()
        else:
            self.state = {
                "version": 1,
                "balance": str(self.initial_balance),
                "positions": {},
                "trades": [],
            }
            self._save()

    @staticmethod
    def _d(value):
        result = Decimal(str(value))
        if not result.is_finite():
            raise ValueError("Non-finite numeric value")
        return result

    def _load(self):
        with self.path.open("r", encoding="utf-8") as f:
            state = json.load(f)
        if not isinstance(state, dict):
            raise ValueError("Invalid paper state")
        if not isinstance(state.get("positions"), dict):
            raise ValueError("Invalid positions")
        if not isinstance(state.get("trades"), list):
            raise ValueError("Invalid trades")
        balance = self._d(state.get("balance"))
        if balance < 0:
            raise ValueError("Invalid balance")
        return state

    def _save(self):
        temp = self.path.with_suffix(".tmp")
        with temp.open("w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, self.path)

    def _commit(self, old_state):
        try:
            self._save()
        except Exception:
            self.state = old_state
            raise

    def _validate(self, domain, symbol, price):
        domain = str(domain).strip().lower()
        symbol = str(symbol).strip().upper()
        price = self._d(price)
        if domain not in self.DOMAINS:
            raise ValueError("Unsupported trading domain")
        if not symbol or price <= 0:
            raise ValueError("Invalid symbol or price")
        return domain, symbol, price

    def open_position(
        self, domain, symbol, direction, price, quantity,
        leverage=1, stop_loss=None, take_profit=None
    ):
        domain, symbol, price = self._validate(domain, symbol, price)
        direction = str(direction).strip().upper()
        quantity = self._d(quantity)
        leverage = self._d(leverage)

        if direction not in ("BUY", "LONG", "SHORT"):
            return {"success": False, "reason": "Invalid direction"}
        if domain in ("spot", "alpha") and direction != "BUY":
            return {"success": False, "reason": "Spot positions only support BUY"}
        if quantity <= 0 or leverage < 1:
            return {"success": False, "reason": "Invalid quantity or leverage"}
        if domain != "futures" and leverage != 1:
            return {"success": False, "reason": "Leverage is futures-only"}

        fill = price * (
            1 + self.slippage_rate if direction in ("BUY", "LONG")
            else 1 - self.slippage_rate
        )
        notional = fill * quantity
        fee = notional * self.fee_rate
        margin = notional / leverage if domain == "futures" else notional
        required = margin + fee

        sl = self._d(stop_loss) if stop_loss is not None else None
        tp = self._d(take_profit) if take_profit is not None else None
        if sl is not None and sl <= 0:
            return {"success": False, "reason": "Invalid stop loss"}
        if tp is not None and tp <= 0:
            return {"success": False, "reason": "Invalid take profit"}

        key = f"{domain}:{symbol}:{uuid.uuid4().hex[:12]}"

        with self.lock:
            old = json.loads(json.dumps(self.state))
            balance = self._d(self.state["balance"])
            if required > balance:
                return {"success": False, "reason": "Insufficient paper balance"}

            position = {
                "id": key,
                "domain": domain,
                "symbol": symbol,
                "direction": direction,
                "entry_price": str(fill),
                "quantity": str(quantity),
                "remaining_quantity": str(quantity),
                "leverage": str(leverage),
                "margin": str(margin),
                "entry_fee": str(fee),
                "stop_loss": str(sl) if sl is not None else None,
                "take_profit": str(tp) if tp is not None else None,
                "status": "OPEN",
            }
            self.state["balance"] = str(balance - required)
            self.state["positions"][key] = position
            self.state["trades"].append({
                "id": f"paper_{uuid.uuid4().hex}",
                "action": "OPEN",
                "position_id": key,
                "domain": domain,
                "symbol": symbol,
                "direction": direction,
                "price": str(fill),
                "quantity": str(quantity),
                "fee": str(fee),
            })
            self._commit(old)
            return {"success": True, "position": position}

    def close_position(self, position_id, price, quantity=None, reason='MANUAL'):
        price = self._d(price)
        if price <= 0:
            return {"success": False, "reason": "Invalid exit price"}

        with self.lock:
            position = self.state["positions"].get(position_id)
            if not position or position["status"] != "OPEN":
                return {"success": False, "reason": "Position not found or closed"}

            old = json.loads(json.dumps(self.state))
            held = self._d(position["remaining_quantity"])
            qty = held if quantity is None else self._d(quantity)
            if qty <= 0 or qty > held:
                return {"success": False, "reason": "Invalid close quantity"}

            direction = position["direction"]
            fill = price * (
                1 - self.slippage_rate if direction in ("BUY", "LONG")
                else 1 + self.slippage_rate
            )
            entry = self._d(position["entry_price"])
            leverage = self._d(position["leverage"])
            notional = fill * qty
            exit_fee = notional * self.fee_rate
            entry_fee_part = self._d(position["entry_fee"]) * (
                qty / self._d(position["quantity"])
            )

            if direction in ("BUY", "LONG"):
                gross_pnl = (fill - entry) * qty
            else:
                gross_pnl = (entry - fill) * qty

            pnl = gross_pnl - exit_fee - entry_fee_part
            margin_part = self._d(position["margin"]) * (
                qty / self._d(position["quantity"])
            )
            returned = margin_part + gross_pnl - exit_fee

            if position["domain"] != "futures":
                returned = notional - exit_fee

            self.state["balance"] = str(
                self._d(self.state["balance"]) + returned
            )
            remaining = held - qty
            position["remaining_quantity"] = str(remaining)
            if remaining == 0:
                position["status"] = "CLOSED"

            trade = {
                "id": f"paper_{uuid.uuid4().hex}",
                "action": "CLOSE",
                "position_id": position_id,
                "domain": position["domain"],
                "symbol": position["symbol"],
                "price": str(fill),
                "quantity": str(qty),
                "fee": str(exit_fee),
                "realized_pnl": str(pnl),
                "reason": str(reason).upper(),
            }
            self.state["trades"].append(trade)
            self._commit(old)
            return {
                "success": True,
                "trade": trade,
                "realized_pnl": str(pnl),
                "remaining_quantity": str(remaining),
                "balance": self.state["balance"],
            }

    def get_status(self):
        with self.lock:
            positions = [
                dict(p) for p in self.state["positions"].values()
                if p["status"] == "OPEN"
            ]
            return {
                "mode": "PAPER",
                "balance": self.state["balance"],
                "open_positions": positions,
                "open_count": len(positions),
                "total_trades": len(self.state["trades"]),
            }

    def get_trade_history(self, limit=100):
        with self.lock:
            limit = max(1, min(int(limit), 1000))
            return list(self.state["trades"][-limit:])
