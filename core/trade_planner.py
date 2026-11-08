from math import isfinite


class TradePlanner:
    TIMEFRAME_PRIORITY = ("15m", "5m", "1h", "1m")
    MIN_STOP_ATR = 0.75

    @staticmethod
    def _value(frame, aliases):
        if frame is None or not hasattr(frame, "columns") or len(frame) == 0:
            return None
        columns = {
            str(c).strip().lower().replace(" ", "_"): c
            for c in frame.columns
        }
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

    def create(self, agent_data, direction, min_reward_risk=1.5):
        direction = str(direction).strip().upper()
        if direction not in ("LONG", "SHORT"):
            return {"success": False, "reason": "Invalid direction"}

        try:
            min_reward_risk = float(min_reward_risk)
        except (TypeError, ValueError):
            return {"success": False, "reason": "Invalid minimum reward/risk"}
        if not isfinite(min_reward_risk) or min_reward_risk <= 0:
            return {"success": False, "reason": "Invalid minimum reward/risk"}

        selected = None
        for tf in self.TIMEFRAME_PRIORITY:
            frame = agent_data.get(tf)
            entry = self._value(frame, ("close",))
            atr = self._value(frame, ("atr", "atr_14", "atr14"))
            if entry is not None and atr is not None:
                selected = (tf, frame, entry, atr)
                break

        if selected is None:
            return {
                "success": False,
                "reason": "Missing candle Close or ATR data",
            }

        tf, frame, entry, atr = selected
        support = self._value(
            frame, ("support", "support_20", "support_level", "swing_low")
        )
        resistance = self._value(
            frame, ("resistance", "resistance_20",
                    "resistance_level", "swing_high")
        )

        buffer = 0.15 * atr
        atr_distance = 1.5 * atr

        if direction == "LONG":
            stop = entry - atr_distance
            if support is not None and support < entry:
                structural_stop = support - buffer
                structural_distance = entry - structural_stop
                if structural_distance >= self.MIN_STOP_ATR * atr:
                    stop = max(stop, structural_stop)

            risk = entry - stop
            target = entry + 2.0 * risk
            if resistance is not None and resistance > entry:
                target = resistance - buffer
        else:
            stop = entry + atr_distance
            if resistance is not None and resistance > entry:
                structural_stop = resistance + buffer
                structural_distance = structural_stop - entry
                if structural_distance >= self.MIN_STOP_ATR * atr:
                    stop = min(stop, structural_stop)

            risk = stop - entry
            target = entry - 2.0 * risk
            if support is not None and support < entry:
                target = support + buffer

        if not isfinite(risk) or risk <= 0 or not isfinite(target) or target <= 0:
            return {"success": False, "reason": "Invalid calculated levels"}

        if direction == "LONG" and not stop < entry < target:
            return {
                "success": False,
                "reason": "Resistance leaves no valid LONG target",
            }
        if direction == "SHORT" and not target < entry < stop:
            return {
                "success": False,
                "reason": "Support leaves no valid SHORT target",
            }

        ratio = abs(target - entry) / risk
        if not isfinite(ratio) or ratio < min_reward_risk:
            return {
                "success": False,
                "reason": "Reward/risk below minimum after structural levels",
                "reward_risk": round(ratio, 3) if isfinite(ratio) else None,
            }

        return {
            "success": True,
            "symbol": str(agent_data.get("symbol", "")).upper(),
            "direction": direction,
            "timeframe": tf,
            "entry": entry,
            "stop_loss": stop,
            "take_profit": target,
            "atr": atr,
            "support": support,
            "resistance": resistance,
            "risk_distance": risk,
            "reward_risk": round(ratio, 3),
            "method": "ATR + support/resistance",
        }
