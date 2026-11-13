"""ATR + confirmed candle-structure trailing stop calculations.

The stop only tightens. It never moves away from the market or increases
the risk on an already-open position.
"""
from math import isfinite


def calculate_trailing_stop(frame, direction, previous_stop, best_price,
                            current_price, atr_period=14,
                            atr_multiple=1.5, swing_lookback=5):
    if frame is None or len(frame) < atr_period + 2:
        return None
    columns = {str(c).strip().lower(): c for c in frame.columns}
    if not all(k in columns for k in ("high", "low", "close")):
        return None
    try:
        highs = [float(v) for v in frame[columns["high"]].tail(atr_period + 1)]
        lows = [float(v) for v in frame[columns["low"]].tail(atr_period + 1)]
        closes = [float(v) for v in frame[columns["close"]].tail(atr_period + 1)]
        if not all(isfinite(v) and v > 0 for v in highs + lows + closes):
            return None
        ranges = []
        for i in range(1, len(closes)):
            ranges.append(max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            ))
        atr = sum(ranges[-atr_period:]) / min(atr_period, len(ranges))
        if not isfinite(atr) or atr <= 0:
            return None
        direction = str(direction).upper()
        previous = float(previous_stop)
        current = float(current_price)
        best = float(best_price or current)
        recent_highs = highs[-swing_lookback:]
        recent_lows = lows[-swing_lookback:]
        if direction == "LONG":
            best = max(best, current, max(recent_highs))
            structure = min(recent_lows) - 0.20 * atr
            candidate = max(structure, best - atr_multiple * atr)
            tightened = max(previous, candidate)
        elif direction == "SHORT":
            best = min(best, current, min(recent_lows))
            structure = max(recent_highs) + 0.20 * atr
            candidate = min(structure, best + atr_multiple * atr)
            tightened = min(previous, candidate)
        else:
            return None
        if not isfinite(tightened) or tightened <= 0:
            return None
        return {
            "stop": tightened,
            "best_price": best,
            "atr": atr,
            "structure_level": structure,
            "method": "ATR_1.5x_PLUS_5_CANDLE_STRUCTURE",
        }
    except (TypeError, ValueError, ArithmeticError, IndexError, KeyError):
        return None
