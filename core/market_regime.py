"""Causal, ATR-normalized market regime classification for closed 1h candles."""
from math import isfinite


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
