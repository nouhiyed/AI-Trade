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


class MarketRegimeEngine:
    MIN_ADX = 18.0
    STRONG_ADX = 25.0
    MIN_SLOPE_ATR = 0.15
    MIN_EMA_SPREAD_ATR = 0.35
    VOLATILITY_SHOCK_MULTIPLE = 2.5
    VOLATILITY_LOOKBACK = 96

    @staticmethod
    def _column(frame, name):
        if frame is None or not hasattr(frame, "columns"):
            return None
        lookup = {str(c).strip().lower().replace(" ", "_"): c for c in frame.columns}
        return lookup.get(name.lower().replace(" ", "_"))

    @classmethod
    def _value(cls, frame, name, index=-1):
        col = cls._column(frame, name)
        if col is None:
            return None
        try:
            value = float(frame[col].iloc[index])
            return value if isfinite(value) else None
        except (TypeError, ValueError, IndexError, KeyError):
            return None

    @classmethod
    def classify(cls, frame):
        if frame is None or len(frame) < 205:
            return cls._result("UNKNOWN", "Need at least 205 closed 1h candles")
        close = cls._value(frame, "close")
        ema50 = cls._value(frame, "EMA_50")
        ema200 = cls._value(frame, "EMA_200")
        ema50_old = cls._value(frame, "EMA_50", -6)
        adx = cls._value(frame, "ADX")
        atr = cls._value(frame, "ATR")
        if None in (close, ema50, ema200, ema50_old, atr) or atr <= 0:
            return cls._result("UNKNOWN", "Missing or invalid close, EMA, or ATR data")

        atr_median = None
        atr_col = cls._column(frame, "ATR")
        if atr_col is not None:
            try:
                values = frame[atr_col].tail(cls.VOLATILITY_LOOKBACK).astype(float)
                values = values[values.map(isfinite)]
                if len(values) >= 30:
                    atr_median = float(values.median())
            except (TypeError, ValueError):
                pass
        volatility_ratio = atr / atr_median if atr_median and atr_median > 0 else None
        slope_atr = (ema50 - ema50_old) / atr
        spread_atr = (ema50 - ema200) / atr
        plus_di = cls._value(frame, "PLUS_DI")
        if plus_di is None:
            plus_di = cls._value(frame, "+DI")
        if plus_di is None:
            plus_di = cls._value(frame, "ADX_pos")
        minus_di = cls._value(frame, "MINUS_DI")
        if minus_di is None:
            minus_di = cls._value(frame, "-DI")
        if minus_di is None:
            minus_di = cls._value(frame, "ADX_neg")
        common = dict(adx=adx, slope_atr=slope_atr, spread_atr=spread_atr,
                      volatility_ratio=volatility_ratio, plus_di=plus_di, minus_di=minus_di)

        if volatility_ratio is not None and volatility_ratio >= cls.VOLATILITY_SHOCK_MULTIPLE:
            return cls._result("HIGH_VOLATILITY",
                f"1h ATR is {volatility_ratio:.2f}x its recent median; entries paused",
                allow_trade=False, **common)
        if adx is None:
            return cls._result("UNKNOWN", "ADX is unavailable", **common)
        if adx < cls.MIN_ADX:
            return cls._result("RANGE", f"ADX {adx:.2f} below {cls.MIN_ADX:.1f}", **common)

        bull = (close > ema200 and ema50 > ema200
                and slope_atr >= cls.MIN_SLOPE_ATR
                and spread_atr >= cls.MIN_EMA_SPREAD_ATR
                and (plus_di is None or minus_di is None or plus_di > minus_di))
        bear = (close < ema200 and ema50 < ema200
                and slope_atr <= -cls.MIN_SLOPE_ATR
                and spread_atr <= -cls.MIN_EMA_SPREAD_ATR
                and (plus_di is None or minus_di is None or minus_di > plus_di))
        if bull or bear:
            regime = "BULLISH" if bull else "BEARISH"
            strength = "STRONG" if adx >= cls.STRONG_ADX else "WEAK"
            return cls._result(regime,
                f"{strength} {regime.lower()} trend; ADX={adx:.1f}, "
                f"EMA slope={slope_atr:.2f} ATR, EMA spread={spread_atr:.2f} ATR",
                strength=strength, allow_trade=True, **common)
        return cls._result("TRANSITION",
            "Trend alignment, normalized slope, EMA spread, or DI confirmation is incomplete",
            allow_trade=False, **common)

    @staticmethod
    def _result(regime, reason, **values):
        result = {"regime": regime, "reason": reason, "allow_trade": False}
        result.update(values)
        return result
