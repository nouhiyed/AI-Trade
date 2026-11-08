import json
import os
import threading

from pathlib import Path
from datetime import datetime, timezone


class RiskManager:

    def __init__(
        self,
        initial_balance=1000.0,
        max_daily_loss_pct=3.0,
        max_total_risk_pct=2.0
    ):
        self.lock = threading.RLock()

        self.state_file = Path("config/risk_state.json")

        self.balance = float(initial_balance)
        self.equity = float(initial_balance)

        self.max_daily_loss_pct = float(max_daily_loss_pct)
        self.max_total_risk_pct = float(max_total_risk_pct)

        self.daily_loss = 0.0
        self.reservations = {}

        self.domains = {
            "futures": {"enabled": True},
            "spot": {"enabled": True},
            "alpha": {"enabled": True}
        }

        self.day = datetime.now(timezone.utc).date()
        self.trade_counter = 0

        self.load_state()

    # -------------------------
    # SAVE STATE
    # -------------------------

    def save_state(self):

        with self.lock:

            self.state_file.parent.mkdir(
                parents=True,
                exist_ok=True
            )

            state = {
                "balance": self.balance,
                "equity": self.equity,
                "daily_loss": self.daily_loss,
                "day": self.day.isoformat(),
                "reservations": self.reservations,
                "domains": self.domains,
                "trade_counter": self.trade_counter
            }

            temp_file = self.state_file.with_suffix(".tmp")

            with open(temp_file, "w") as file:
                json.dump(state, file, indent=4)

                file.flush()
                os.fsync(file.fileno())

            os.replace(temp_file, self.state_file)

    # -------------------------
    # LOAD STATE
    # -------------------------

    def load_state(self):

        with self.lock:

            if not self.state_file.exists():
                self.save_state()
                return

            try:
                with open(self.state_file, "r") as file:
                    state = json.load(file)

                self.balance = float(state["balance"])
                self.equity = float(state["equity"])
                self.daily_loss = float(state["daily_loss"])

                self.day = datetime.fromisoformat(
                    state["day"]
                ).date()

                self.reservations = state["reservations"]
                self.trade_counter = int(
                    state.get("trade_counter", 0)
                )

                saved_domains = state.get("domains", {})

                for domain in self.domains:
                    if domain in saved_domains:
                        self.domains[domain]["enabled"] = bool(
                            saved_domains[domain]["enabled"]
                        )

                if not isinstance(self.reservations, dict):
                    raise ValueError("Invalid reservations")

                print("Risk state restored successfully.")

            except Exception as error:
                raise RuntimeError(
                    f"Risk state could not be loaded: {error}. "
                    "Existing state was not overwritten."
                )

    # -------------------------
    # DAILY RESET
    # -------------------------

    def reset_daily_if_needed(self):

        today = datetime.now(timezone.utc).date()

        if today != self.day:
            self.day = today
            self.daily_loss = 0.0
            self.save_state()

    # -------------------------
    # BALANCE MANAGEMENT
    # -------------------------

    def get_reserved_margin(self):

        return sum(
            item["margin"]
            for item in self.reservations.values()
        )

    def get_reserved_risk(self):

        return sum(
            item["risk"]
            for item in self.reservations.values()
        )

    def get_available_balance(self):

        return max(
            0.0,
            self.balance - self.get_reserved_margin()
        )

    # -------------------------
    # RESERVE TRADE
    # -------------------------

    def reserve_trade(
        self,
        domain,
        symbol,
        direction,
        entry,
        stop_loss,
        risk_pct=0.5,
        leverage=1
    ):

        with self.lock:

            self.reset_daily_if_needed()

            if domain not in self.domains:
                return {"approved": False, "reason": "Unknown domain"}

            if not self.domains[domain]["enabled"]:
                return {"approved": False, "reason": "Domain disabled"}

            if entry <= 0 or stop_loss <= 0:
                return {"approved": False, "reason": "Invalid prices"}

            if direction not in ["LONG", "SHORT"]:
                return {"approved": False, "reason": "Invalid direction"}

            try:
                risk_pct = float(risk_pct)
                leverage = int(leverage)
            except (TypeError, ValueError):
                return {"approved": False, "reason": "Invalid risk settings"}

            if risk_pct <= 0 or leverage < 1:
                return {"approved": False, "reason": "Invalid risk settings"}
            if domain == "futures" and leverage > 5:
                return {"approved": False, "reason": "Futures leverage exceeds the hard 5x limit"}
            if domain in ("spot", "alpha") and leverage != 1:
                return {"approved": False, "reason": "Spot and Alpha must use 1x leverage"}

            if direction == "LONG" and stop_loss >= entry:
                return {"approved": False, "reason": "Invalid LONG stop"}

            if direction == "SHORT" and stop_loss <= entry:
                return {"approved": False, "reason": "Invalid SHORT stop"}

            max_daily_loss = (
                self.balance * self.max_daily_loss_pct / 100
            )

            remaining_daily_loss = (
                max_daily_loss - self.daily_loss
            )

            if remaining_daily_loss <= 0:
                return {"approved": False, "reason": "Daily loss limit reached"}

            max_total_risk = (
                self.equity * self.max_total_risk_pct / 100
            )

            remaining_risk = (
                max_total_risk - self.get_reserved_risk()
            )

            risk_amount = min(
                self.equity * risk_pct / 100,
                remaining_risk,
                remaining_daily_loss
            )

            if risk_amount <= 0:
                return {"approved": False, "reason": "Risk limit reached"}

            stop_distance = abs(entry - stop_loss) / entry

            if stop_distance <= 0:
                return {"approved": False, "reason": "Invalid stop distance"}

            notional = risk_amount / stop_distance
            margin = notional / leverage

            if margin > self.get_available_balance():
                return {
                    "approved": False,
                    "reason": "Insufficient shared balance"
                }

            quantity = notional / entry

            self.trade_counter += 1

            trade_id = (
                f"{domain}_{symbol}_{self.trade_counter}"
            )

            reservation = {
                "trade_id": trade_id,
                "domain": domain,
                "symbol": symbol,
                "direction": direction,
                "entry": entry,
                "stop_loss": stop_loss,
                "quantity": quantity,
                "notional": notional,
                "margin": margin,
                "risk": risk_amount,
                "leverage": leverage,
                "status": "RESERVED"
            }

            self.reservations[trade_id] = reservation

            self.save_state()

            return {
                "approved": True,
                **reservation
            }

    def update_reservation_status(self, trade_id, status, **metadata):
        """Persist an execution lifecycle status without releasing risk."""
        allowed = {
            "RESERVED", "DEMO_PENDING", "DEMO_OPEN", "DEMO_PARTIALLY_CLOSED",
            "DEMO_UNPROTECTED", "DEMO_RECONCILIATION_REQUIRED",
            "LIVE_PENDING", "LIVE_OPEN",
        }
        status = str(status).upper()
        if status not in allowed:
            return {"success": False, "reason": "Invalid reservation status"}

        with self.lock:
            trade = self.reservations.get(str(trade_id))
            if trade is None:
                return {"success": False, "reason": "Trade not found"}

            trade["status"] = status
            for key, value in metadata.items():
                if key not in ("trade_id", "risk", "margin", "quantity"):
                    trade[key] = value

            self.save_state()
            return {"success": True, "trade": dict(trade)}

    def release_reservation(self, trade_id):
        """Release a reservation only when execution is confirmed not to have opened."""
        with self.lock:
            trade = self.reservations.get(str(trade_id))
            if trade is None:
                return {"success": False, "reason": "Trade not found"}
            if trade.get("status") != "DEMO_PENDING":
                return {"success": False, "reason": "Reservation is not pending"}
            self.reservations.pop(str(trade_id))
            self.save_state()
            return {"success": True, "trade_id": str(trade_id)}

    def sync_balance(self, balance):
        """Align the risk balance with the real (testnet) account when nothing is reserved."""
        with self.lock:
            if self.reservations:
                return False
            try:
                value = float(balance)
            except (TypeError, ValueError):
                return False
            if not value > 0 or value != value or value == float("inf"):
                return False
            self.balance = value
            self.equity = value
            self.save_state()
            return True

    # -------------------------
    # CLOSE TRADE
    # -------------------------

    def close_trade(self, trade_id, realized_pnl):

        with self.lock:

            if trade_id not in self.reservations:
                return {
                    "success": False,
                    "reason": "Trade not found"
                }

            realized_pnl = float(realized_pnl)

            trade = self.reservations.pop(trade_id)

            self.balance += realized_pnl
            self.equity += realized_pnl

            if realized_pnl < 0:
                self.daily_loss += abs(realized_pnl)

            self.save_state()

            return {
                "success": True,
                "trade_id": trade_id,
                "realized_pnl": realized_pnl,
                "balance": self.balance
            }

    # -------------------------
    # DOMAIN CONTROL
    # -------------------------

    def set_domain(self, domain, enabled):

        with self.lock:

            if domain not in self.domains:
                return False

            self.domains[domain]["enabled"] = bool(enabled)

            self.save_state()

            return True

    # -------------------------
    # EMERGENCY STOP
    # -------------------------

    def emergency_stop(self):

        with self.lock:

            for domain in self.domains:
                self.domains[domain]["enabled"] = False

            self.save_state()

    # -------------------------
    # STATUS
    # -------------------------

    def get_status(self):

        with self.lock:

            self.reset_daily_if_needed()

            return {
                "balance": round(self.balance, 2),
                "equity": round(self.equity, 2),

                "available_balance": round(
                    self.get_available_balance(), 2
                ),

                "reserved_margin": round(
                    self.get_reserved_margin(), 2
                ),

                "reserved_risk": round(
                    self.get_reserved_risk(), 2
                ),

                "daily_loss": round(self.daily_loss, 2),

                "domains": self.domains,

                "active_reservations": len(
                    self.reservations
                )
            }

