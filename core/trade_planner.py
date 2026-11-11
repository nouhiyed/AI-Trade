"""Fast-trade planning around the nearest confirmed market structure.

Targets are placed before the nearest opposing liquidity/structure zone. A
second target is exposed only when a distinct next zone exists and is worth
trading after estimated round-trip costs. Prices are estimates; DEMO execution
still uses executable bid/ask quotes.
"""
from math import isfinite


class TradePlanner:
    TIMEFRAME_PRIORITY = ("5m", "1m", "15m", "1h")
    MIN_STOP_ATR = 0.75
    FEE_RATE = 0.001
    SLIPPAGE_RATE = 0.0005
    TARGET_BUFFER_ATR = 0.12

    @staticmethod
    def _value(frame, aliases):
        if frame is None or not hasattr(frame, "columns") or len(frame) == 0:
            return None
        columns = {str(c).strip().lower().replace(" ", "_"): c for c in frame.columns}
        for alias in aliases:
            column = columns.get(alias.lower().replace(" ", "_"))
            if column is not None:
                try:
                    value = float(frame[column].iloc[-1])
                    if isfinite(value) and value > 0:
                        return value
                except (TypeError, ValueError, IndexError, KeyError):
                    pass
        return None

    @staticmethod
    def _levels(frame, side, entry, lookback=120, radius=2):
        """Return nearest and next confirmed local swing levels around entry."""
        if frame is None or not hasattr(frame, "columns"):
            return []
        cols = {str(c).strip().lower(): c for c in frame.columns}
        column = cols.get("low" if side == "support" else "high")
        if column is None:
            return []
        try:
            values = [float(v) for v in frame[column].tail(lookback).tolist()]
        except (TypeError, ValueError):
            return []
        found = []
        # Ignore the newest two candles so a pivot is confirmed, not repainting.
        for i in range(radius, len(values) - radius - 2):
            value = values[i]
            window = values[i-radius:i+radius+1]
            is_pivot = value == min(window) if side == "support" else value == max(window)
            if not is_pivot:
                continue
            if side == "support" and value < entry:
                found.append(value)
            elif side == "resistance" and value > entry:
                found.append(value)
        found.sort(reverse=(side == "resistance"))
        unique = []
        for value in found:
            if not any(abs(value - old) / max(abs(old), 1e-12) < 0.0015 for old in unique):
                unique.append(value)
        return unique[:6]

    def create(self, agent_data, direction, min_reward_risk=1.0,
               preferred_timeframe=None, fee_rate=None, slippage_rate=None):
        direction = str(direction).strip().upper()
        if direction not in ("LONG", "SHORT"):
            return {"success": False, "reason": "Invalid direction"}
        try:
            min_reward_risk = float(min_reward_risk)
            fee = self.FEE_RATE if fee_rate is None else float(fee_rate)
            slip = self.SLIPPAGE_RATE if slippage_rate is None else float(slippage_rate)
        except (TypeError, ValueError):
            return {"success": False, "reason": "Invalid cost or reward/risk settings"}
        if not all(isfinite(v) and v >= 0 for v in (min_reward_risk, fee, slip)) or min_reward_risk <= 0:
            return {"success": False, "reason": "Invalid cost or reward/risk settings"}

        preferred = str(preferred_timeframe or "").strip().lower()
        order = ((preferred,) if preferred and preferred in agent_data else ()) + tuple(
            tf for tf in self.TIMEFRAME_PRIORITY if tf != preferred)
        selected = None
        for tf in order:
            frame = agent_data.get(tf)
            entry = self._value(frame, ("close",))
            atr = self._value(frame, ("atr", "atr_14", "atr14"))
            if entry and atr:
                selected = (tf, frame, entry, atr)
                break
        if selected is None:
            return {"success": False, "reason": "Missing candle Close or ATR data"}

        tf, frame, entry, atr = selected
        supports = self._levels(frame, "support", entry)
        resistances = self._levels(frame, "resistance", entry)
        fallback_support = self._value(frame, ("support", "support_20", "support_level", "swing_low"))
        fallback_resistance = self._value(frame, ("resistance", "resistance_20", "resistance_level", "swing_high"))
        if not supports and fallback_support and fallback_support < entry:
            supports = [fallback_support]
        if not resistances and fallback_resistance and fallback_resistance > entry:
            resistances = [fallback_resistance]

        buffer = max(0.12 * atr, entry * 0.0002)
        min_stop = self.MIN_STOP_ATR * atr
        round_trip_cost_pct = 2.0 * (fee + slip)

        if direction == "SHORT":
            if not supports:
                return {"success": False, "reason": "No confirmed support below entry; refusing to invent a distant target"}
            target1 = supports[0] + buffer
            target2 = supports[1] + buffer if len(supports) > 1 else None
            resistance = resistances[0] if resistances else None
            structural_stop = resistance + buffer if resistance else entry + 1.5 * atr
            stop = max(structural_stop, entry + min_stop)
            risk = stop - entry
            reward = entry - target1
        else:
            if not resistances:
                return {"success": False, "reason": "No confirmed resistance above entry; refusing to invent a distant target"}
            target1 = resistances[0] - buffer
            target2 = resistances[1] - buffer if len(resistances) > 1 else None
            support = supports[0] if supports else None
            structural_stop = support - buffer if support else entry - 1.5 * atr
            stop = min(structural_stop, entry - min_stop)
            risk = entry - stop
            reward = target1 - entry

        if not all(isfinite(v) and v > 0 for v in (entry, stop, target1, risk, reward)):
            return {"success": False, "reason": "Invalid calculated structural levels"}
        if direction == "SHORT" and not target1 < entry < stop:
            return {"success": False, "reason": "Invalid SHORT support/resistance ordering"}
        if direction == "LONG" and not stop < entry < target1:
            return {"success": False, "reason": "Invalid LONG support/resistance ordering"}

        gross_reward_pct = reward / entry
        gross_risk_pct = risk / entry
        net_reward_pct = gross_reward_pct - round_trip_cost_pct
        net_risk_pct = gross_risk_pct + round_trip_cost_pct
        if net_reward_pct <= 0:
            return {"success": False, "reason": "Nearest target does not cover estimated round-trip fees and slippage",
                    "estimated_net_reward_pct": round(net_reward_pct * 100, 4)}
        net_rr = net_reward_pct / net_risk_pct if net_risk_pct > 0 else 0
        if net_rr < min_reward_risk:
            return {"success": False, "reason": "Nearest structural target has insufficient net reward/risk after costs",
                    "net_reward_risk": round(net_rr, 3),
                    "estimated_net_reward_pct": round(net_reward_pct * 100, 4)}

        # Keep TP2 only if it is farther in the profitable direction and still
        # provides positive net proceeds after another round trip.
        if target2 is not None:
            extra_move = entry - target2 if direction == "SHORT" else target2 - entry
            if extra_move / entry <= round_trip_cost_pct or (
                direction == "SHORT" and target2 >= target1
            ) or (direction == "LONG" and target2 <= target1):
                target2 = None

        return {
            "success": True, "symbol": str(agent_data.get("symbol", "")).upper(),
            "direction": direction, "timeframe": tf, "entry": entry,
            "stop_loss": stop, "take_profit": target1, "take_profit_2": target2,
            "tp1_close_pct": 70 if target2 is not None else 100,
            "atr": atr, "support": supports[0] if supports else None,
            "next_support": supports[1] if len(supports) > 1 else None,
            "resistance": resistances[0] if resistances else None,
            "next_resistance": resistances[1] if len(resistances) > 1 else None,
            "risk_distance": risk, "reward_risk": round(reward / risk, 3),
            "net_reward_risk": round(net_rr, 3),
            "estimated_round_trip_cost_pct": round(round_trip_cost_pct * 100, 4),
            "estimated_net_reward_pct": round(net_reward_pct * 100, 4),
            "method": "Nearest confirmed swing support/resistance + net-cost filter",
        }
