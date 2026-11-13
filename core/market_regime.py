"""Causal multi-timeframe market regime and trendline confirmation helpers."""
from math import isfinite


def _col(frame, name):
    lookup = {str(c).strip().lower().replace(" ", "_"): c for c in frame.columns}
    return lookup.get(name.lower().replace(" ", "_"))


def _last(frame, name):
    column = _col(frame, name)
    if column is None or len(frame) == 0:
        return None
    try:
        value = float(frame[column].iloc[-1])
        return value if isfinite(value) else None
    except (TypeError, ValueError, IndexError):
        return None


def classify_market_regime(market_data):
    """Classify using 1h/15m/5m evidence; missing indicators remain neutral."""
    votes = []
    for tf, weight in (("1h", 3), ("15m", 2), ("5m", 1)):
        frame = market_data.get(tf)
        if frame is None or len(frame) < 30:
            continue
        close = _last(frame, "close")
        ema20 = _last(frame, "EMA_20") or _last(frame, "ema20")
        ema50 = _last(frame, "EMA_50") or _last(frame, "ema50")
        ema200 = _last(frame, "EMA_200") or _last(frame, "ema200")
        adx = _last(frame, "ADX") or _last(frame, "adx")
        if close is None:
            continue
        score = 0
        evidence = 0
        if ema20 and ema50:
            score += 1 if ema20 > ema50 else -1 if ema20 < ema50 else 0
            evidence += 1
        if ema200:
            score += 1 if close > ema200 else -1 if close < ema200 else 0
            evidence += 1
        if len(frame) >= 6:
            previous = float(frame[_col(frame, "close")].iloc[-6])
            if previous > 0:
                slope = (close - previous) / previous
                score += 1 if slope > 0.001 else -1 if slope < -0.001 else 0
                evidence += 1
        if evidence:
            strength = 0.5 if adx is not None and adx < 18 else 1.0
            votes.append((score / evidence) * weight * strength)
    total = sum(weight for _, weight in (("1h", 3), ("15m", 2), ("5m", 1))
                if market_data.get(_))
    if not votes:
        regime, confidence = "RANGING", 0.0
    else:
        score = sum(votes)
        maximum = 6.0
        confidence = min(100.0, abs(score) / maximum * 100.0)
        if score >= 1.5:
            regime = "BULLISH"
        elif score <= -1.5:
            regime = "BEARISH"
        else:
            regime = "RANGING"
    def recent_flag(frame, names, expected=None):
        if frame is None:
            return False
        for name in names:
            column = _col(frame, name)
            if column is None:
                continue
            for value in frame[column].tail(3).tolist():
                if expected and str(value).strip().upper() == expected:
                    return True
                if not expected and bool(value):
                    return True
        return False
    fast = market_data.get("5m")
    bullish_reversal = recent_flag(fast, ("CHoCH",), "BULLISH") or recent_flag(fast, ("Bullish_Sweep",))
    bearish_reversal = recent_flag(fast, ("CHoCH",), "BEARISH") or recent_flag(fast, ("Bearish_Sweep",))
    return {
        "regime": regime,
        "confidence": round(confidence, 2),
        "bullish_reversal": bullish_reversal,
        "bearish_reversal": bearish_reversal,
        "timeframes_used": [tf for tf in ("1h", "15m", "5m")
                            if market_data.get(tf) is not None],
    }


def trendline_retest(frame, direction, atr):
    """Confirm a causal breakout/retest using pivots only after two right candles."""
    if frame is None or len(frame) < 12 or not atr:
        return {"confirmed": False, "reason": "Insufficient candles for trendline retest"}
    columns = {str(c).strip().lower(): c for c in frame.columns}
    if not all(name in columns for name in ("open", "high", "low", "close")):
        return {"confirmed": False, "reason": "OHLC unavailable for trendline retest"}
    highs = [float(v) for v in frame[columns["high"]].tolist()]
    lows = [float(v) for v in frame[columns["low"]].tolist()]
    closes = [float(v) for v in frame[columns["close"]].tolist()]
    radius = 2
    pivots = []
    for i in range(radius, len(frame) - radius - 2):
        if direction == "LONG":
            window = lows[i-radius:i+radius+1]
            if lows[i] == min(window) and window.count(lows[i]) == 1:
                pivots.append((i, lows[i]))
        else:
            window = highs[i-radius:i+radius+1]
            if highs[i] == max(window) and window.count(highs[i]) == 1:
                pivots.append((i, highs[i]))
    if len(pivots) < 2:
        return {"confirmed": False, "reason": "Two confirmed trendline pivots not available"}
    (i1, p1), (i2, p2) = pivots[-2:]
    if i2 <= i1:
        return {"confirmed": False, "reason": "Invalid trendline pivots"}
    slope = (p2 - p1) / (i2 - i1)
    line = p2 + slope * (len(frame) - 1 - i2)
    tolerance = max(float(atr) * 0.25, abs(line) * 0.00015)
    approach, retest, confirm = -3, -2, -1
    if direction == "LONG":
        broke = closes[approach] > line + tolerance
        touched = lows[retest] <= line + tolerance and closes[retest] >= line
        confirmed = closes[confirm] > highs[retest] and closes[confirm] > opensafe(frame, columns, confirm)
        reason = "Bullish trendline breakout, successful retest and follow-through"
    else:
        broke = closes[approach] < line - tolerance
        touched = highs[retest] >= line - tolerance and closes[retest] <= line
        confirmed = closes[confirm] < lows[retest] and closes[confirm] < opensafe(frame, columns, confirm)
        reason = "Bearish trendline breakdown, failed retest and follow-through"
    return {"confirmed": bool(broke and touched and confirmed), "line": line,
            "pivots": [(i1, p1), (i2, p2)],
            "reason": reason if broke and touched and confirmed
                      else "Trendline break/retest not yet confirmed"}


def opensafe(frame, columns, index):
    return float(frame[columns["open"]].iloc[index])
