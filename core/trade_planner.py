"""Scalping trade plans based on confirmed rejection at market structure."""
from math import isfinite


class TradePlanner:
    TIMEFRAME_PRIORITY = ("5m", "1m", "15m", "1h")
    MIN_STOP_ATR = 0.75
    FEE_RATE = 0.001
    SLIPPAGE_RATE = 0.0005
    TARGET_BUFFER_ATR = 0.12
    MIN_REWARD_RISK = 1.5
    ENTRY_ZONE_ATR = 0.45

    @staticmethod
    def _columns(frame):
        return {str(c).strip().lower().replace(" ", "_"): c for c in frame.columns}

    @classmethod
    def _value(cls, frame, aliases):
        if frame is None or not hasattr(frame, "columns") or len(frame) == 0:
            return None
        columns = cls._columns(frame)
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
    def _levels(frame, side, entry, lookback=160, radius=2):
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
        for i in range(radius, len(values) - radius - 2):
            value = values[i]
            window = values[i-radius:i+radius+1]
            extreme = min(window) if side == "support" else max(window)
            # Flat/equal-price plateaus are zones, not confirmed swing pivots.
            # Count only a unique local extreme to avoid treating every candle
            # in a flat range as a fresh support/resistance level.
            pivot = value == extreme and window.count(value) == 1
            if pivot and ((side == "support" and value < entry) or
                          (side == "resistance" and value > entry)):
                found.append(value)
        found.sort(reverse=(side == "support"))
        unique = []
        for value in found:
            if not any(abs(value-old) / max(abs(old), 1e-12) < 0.0015 for old in unique):
                unique.append(value)
        return unique[:6]

    @staticmethod
    def _entry_style(frame, direction):
        """Classify the confirmed entry family from the same closed-candle SMC data."""
        cols = {str(c).strip().lower(): c for c in frame.columns}
        side = "BULLISH" if direction == "LONG" else "BEARISH"

        def active(column, expected=None):
            name = cols.get(column.lower())
            if name is None:
                return False
            for value in frame[name].tail(5).tolist():
                if expected is not None:
                    if str(value).strip().upper() == expected:
                        return True
                elif bool(value):
                    return True
            return False

        sweep = active("bullish_sweep" if direction == "LONG" else "bearish_sweep")
        choch = active("choch", side)
        bos = active("bos", side)
        if sweep and choch:
            return "liquidity_sweep_reversal"
        if choch:
            return "market_structure_shift"
        if bos:
            return "breakout_retest"
        return "support_resistance_rejection"

    @classmethod
    def _confirmed_rejection(cls, frame, direction, level, atr):
        """Require a structure touch, a rejection candle, then a separate follow-through close."""
        if frame is None or len(frame) < 4 or level is None or atr is None:
            return False, "Not enough closed candles for rejection plus follow-through"
        cols = cls._columns(frame)
        required = ("open", "high", "low", "close")
        if any(name not in cols for name in required):
            return False, "OHLC candle data is missing"
        try:
            candles = [
                {name: float(frame[cols[name]].iloc[i]) for name in required}
                for i in (-3, -2, -1)
            ]
        except (TypeError, ValueError, IndexError):
            return False, "Invalid OHLC confirmation candles"
        approach, rejection, confirm = candles
        near = max(cls.ENTRY_ZONE_ATR * atr, level * 0.00015)
        breakout_buffer = max(0.10 * atr, level * 0.0001)

        if direction == "SHORT":
            touched = abs(rejection["high"] - level) <= near
            rejection_body = abs(rejection["close"] - rejection["open"])
            rejection_span = max(rejection["high"] - rejection["low"], 1e-12)
            upper_wick = rejection["high"] - max(rejection["open"], rejection["close"])
            rejected = (
                rejection["close"] < rejection["open"]
                and rejection["close"] < level
                and upper_wick >= max(rejection_body * 0.5, rejection_span * 0.2)
            )
            broke_out = max(approach["close"], rejection["close"], confirm["close"]) > level + breakout_buffer
            follow_through = (
                confirm["close"] < rejection["low"]
                and confirm["close"] < confirm["open"]
                and confirm["close"] < rejection["close"]
            )
            valid = touched and rejected and follow_through and not broke_out
            if valid:
                return True, "Resistance rejection and bearish follow-through confirmed on closed candles"
            if broke_out:
                reason = "Resistance breakout detected; SHORT blocked until a failed retest"
            elif not touched or not rejected:
                reason = "Waiting for a closed bearish rejection candle at resistance"
            else:
                reason = "Rejection seen; waiting for a separate bearish follow-through close below its low"
            return False, reason

        touched = abs(rejection["low"] - level) <= near
        rejection_body = abs(rejection["close"] - rejection["open"])
        rejection_span = max(rejection["high"] - rejection["low"], 1e-12)
        lower_wick = min(rejection["open"], rejection["close"]) - rejection["low"]
        rejected = (
            rejection["close"] > rejection["open"]
            and rejection["close"] > level
            and lower_wick >= max(rejection_body * 0.5, rejection_span * 0.2)
        )
        broke_down = min(approach["close"], rejection["close"], confirm["close"]) < level - breakout_buffer
        follow_through = (
            confirm["close"] > rejection["high"]
            and confirm["close"] > confirm["open"]
            and confirm["close"] > rejection["close"]
        )
        valid = touched and rejected and follow_through and not broke_down
        if valid:
            return True, "Support rejection and bullish follow-through confirmed on closed candles"
        if broke_down:
            reason = "Support breakdown detected; LONG blocked until a reclaim retest"
        elif not touched or not rejected:
            reason = "Waiting for a closed bullish rejection candle at support"
        else:
            reason = "Rejection seen; waiting for a separate bullish follow-through close above its high"
        return False, reason

    def create(self, agent_data, direction, min_reward_risk=1.5,
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
        if (not all(isfinite(v) and v >= 0 for v in (min_reward_risk, fee, slip))
                or min_reward_risk < self.MIN_REWARD_RISK):
            return {"success": False,
                    "reason": "Minimum net reward/risk cannot be lower than 1.5 after costs"}

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

        if direction == "SHORT" and not resistances:
            return {"success": False, "reason": "No confirmed resistance above entry; SHORT rejected"}
        if direction == "LONG" and not supports:
            return {"success": False, "reason": "No confirmed support below entry; LONG rejected"}
        confirmation_level = resistances[0] if direction == "SHORT" else supports[0]
        confirmed, confirmation_reason = self._confirmed_rejection(
            frame, direction, confirmation_level, atr)
        if not confirmed:
            return {"success": False, "reason": confirmation_reason,
                    "required_level": confirmation_level, "timeframe": tf}

        buffer = max(self.TARGET_BUFFER_ATR * atr, entry * 0.0002)
        min_stop = self.MIN_STOP_ATR * atr
        round_trip_cost_pct = 2.0 * (fee + slip)

        if direction == "SHORT":
            if not supports:
                return {"success": False, "reason": "No confirmed support below entry; SHORT target unavailable"}
            target1 = supports[0] + buffer
            target2 = supports[1] + buffer if len(supports) > 1 else None
            stop = max(resistances[0] + buffer, entry + min_stop)
            risk, reward = stop - entry, entry - target1
        else:
            if not resistances:
                return {"success": False, "reason": "No confirmed resistance above entry; LONG target unavailable"}
            target1 = resistances[0] - buffer
            target2 = resistances[1] - buffer if len(resistances) > 1 else None
            stop = min(supports[0] - buffer, entry - min_stop)
            risk, reward = entry - stop, target1 - entry

        if not all(isfinite(v) and v > 0 for v in (entry, stop, target1, risk, reward)):
            return {"success": False, "reason": "Invalid calculated structural levels"}
        if direction == "SHORT" and not target1 < entry < stop:
            return {"success": False, "reason": "Invalid SHORT support/resistance ordering"}
        if direction == "LONG" and not stop < entry < target1:
            return {"success": False, "reason": "Invalid LONG support/resistance ordering"}

        gross_reward_pct, gross_risk_pct = reward / entry, risk / entry
        net_reward_pct = gross_reward_pct - round_trip_cost_pct
        net_risk_pct = gross_risk_pct + round_trip_cost_pct
        if net_reward_pct <= 0:
            return {"success": False, "reason": "Nearest target cannot cover estimated fees and slippage",
                    "estimated_net_reward_pct": round(net_reward_pct * 100, 4)}
        net_rr = net_reward_pct / net_risk_pct if net_risk_pct > 0 else 0
        if net_rr < min_reward_risk:
            return {"success": False, "reason": "Nearest structure target has insufficient net reward/risk after costs",
                    "net_reward_risk": round(net_rr, 3),
                    "estimated_net_reward_pct": round(net_reward_pct * 100, 4)}

        if target2 is not None:
            extra_move = entry - target2 if direction == "SHORT" else target2 - entry
            if (extra_move / entry <= round_trip_cost_pct or
                (direction == "SHORT" and not target2 < target1) or
                (direction == "LONG" and not target2 > target1)):
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
            "entry_confirmation": confirmation_reason,
            "entry_strategy": self._entry_style(frame, direction),
            "risk_distance": risk, "reward_risk": round(reward / risk, 3),
            "net_reward_risk": round(net_rr, 3),
            "estimated_round_trip_cost_pct": round(round_trip_cost_pct * 100, 4),
            "estimated_net_reward_pct": round(net_reward_pct * 100, 4),
            "method": "Closed-candle rejection at nearest structure; target before opposing zone",
        }
