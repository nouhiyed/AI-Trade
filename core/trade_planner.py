from math import isfinite


class TradePlanner:
    TIMEFRAME_PRIORITY = ("15m", "5m", "1h", "1m")

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

        selected = None
        for tf in self.TIMEFRAME_PRIORITY:
            frame = agent_data.get(tf)
            entry = self._value(frame, ("close",))
            atr = self._value(frame, ("atr", "atr_14", "atr14"))
            if entry and atr:
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

        if direction == "LONG":
            stop = entry - 1.5 * atr
            if support is not None and support < entry:
                stop = min(stop, support - buffer)

            risk = entry - stop
            target = entry + 2 * risk

            if resistance is not None and resistance > entry:
                target = resistance - buffer

        else:
            stop = entry + 1.5 * atr
            if resistance is not None and resistance > entry:
                stop = max(stop, resistance + buffer)

            risk = stop - entry
            target = entry - 2 * risk

            if support is not None and support < entry:
                target = support + buffer

        if risk <= 0 or target <= 0:
            return {"success": False, "reason": "Invalid calculated levels"}

        ratio = abs(target - entry) / risk
        if ratio < float(min_reward_risk):
            return {
                "success": False,
                "reason": "Reward/risk below minimum",
                "reward_risk": round(ratio, 3),
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
