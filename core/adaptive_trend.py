"""Research-first multi-timeframe breakout/retest strategy.

All input frames must contain CLOSED candles only. This module is deliberately
independent from live execution; it returns a plan and never places orders.
"""
from math import isfinite


class AdaptiveTrendStrategy:
    """1h regime + 15m Donchian breakout/retest + 5m confirmation."""

    DONCHIAN_LOOKBACK = 20
    BREAKOUT_SEARCH_BARS = 10
    RETEST_SEARCH_BARS = 4
    MIN_ADX = 18.0
    MIN_VOLUME_RATIO = 1.10
    RETEST_ATR_TOLERANCE = 0.25
    STOP_ATR_BUFFER = 0.20
    MIN_STOP_ATR = 0.75
    MIN_NET_RR = 1.50
    TARGET_R = 2.0
    SLIPPAGE_RATE = 0.0005
    FEES = {"spot": 0.001, "futures": 0.0005}

    @staticmethod
    def _column(frame, name):
        if frame is None or not hasattr(frame, "columns"):
            return None
        lookup = {str(c).strip().lower().replace(" ", "_"): c for c in frame.columns}
        return lookup.get(name.lower().replace(" ", "_"))

    @classmethod
    def _series_value(cls, frame, name, index=-1):
        col = cls._column(frame, name)
        if col is None:
            return None
        try:
            value = float(frame[col].iloc[index])
            return value if isfinite(value) else None
        except (TypeError, ValueError, IndexError, KeyError):
            return None

    @classmethod
    def _regime(cls, frame):
        if frame is None or len(frame) < 205:
            return "UNKNOWN", "Need at least 205 closed 1h candles"
        close = cls._series_value(frame, "close")
        ema50 = cls._series_value(frame, "EMA_50") or cls._series_value(frame, "ema50")
        ema200 = cls._series_value(frame, "EMA_200") or cls._series_value(frame, "ema200")
        ema50_old = cls._series_value(frame, "EMA_50", -6) or cls._series_value(frame, "ema50", -6)
        adx = cls._series_value(frame, "ADX") or cls._series_value(frame, "adx")
        if None in (close, ema50, ema200, ema50_old):
            return "UNKNOWN", "Missing 1h EMA/close data"
        if adx is not None and adx < cls.MIN_ADX:
            return "RANGING", f"1h ADX {adx:.2f} below {cls.MIN_ADX:.1f}"
        if close > ema200 and ema50 > ema200 and ema50 > ema50_old:
            return "BULLISH", "1h close and rising EMA50 above EMA200"
        if close < ema200 and ema50 < ema200 and ema50 < ema50_old:
            return "BEARISH", "1h close and falling EMA50 below EMA200"
        return "RANGING", "1h trend alignment is incomplete"

    @classmethod
    def _find_retest(cls, frame, direction):
        if frame is None or len(frame) < cls.DONCHIAN_LOOKBACK + 8:
            return None, "Not enough 15m candles"
        high_col, low_col = cls._column(frame, "high"), cls._column(frame, "low")
        close_col, open_col = cls._column(frame, "close"), cls._column(frame, "open")
        volume_col = cls._column(frame, "volume")
        atr_col = cls._column(frame, "ATR") or cls._column(frame, "atr")
        if not all((high_col, low_col, close_col, open_col, volume_col, atr_col)):
            return None, "15m OHLCV/ATR columns missing"
        start = max(cls.DONCHIAN_LOOKBACK, len(frame) - cls.BREAKOUT_SEARCH_BARS - cls.RETEST_SEARCH_BARS - 1)
        end = len(frame) - 1
        for breakout_i in range(end - 2, start - 1, -1):
            prior = frame.iloc[breakout_i - cls.DONCHIAN_LOOKBACK:breakout_i]
            level = float(prior[high_col].max() if direction == "LONG" else prior[low_col].min())
            candle = frame.iloc[breakout_i]
            c, o = float(candle[close_col]), float(candle[open_col])
            avg_volume = float(prior[volume_col].mean())
            vol = float(candle[volume_col])
            if avg_volume <= 0 or vol < avg_volume * cls.MIN_VOLUME_RATIO:
                continue
            broke = c > level if direction == "LONG" else c < level
            candle_direction = c > o if direction == "LONG" else c < o
            if not (broke and candle_direction):
                continue
            retest_start = breakout_i + 1
            retest_end = min(end, breakout_i + cls.RETEST_SEARCH_BARS)
            if retest_start > retest_end:
                continue
            for retest_i in range(retest_end, retest_start - 1, -1):
                row = frame.iloc[retest_i]
                atr = float(row[atr_col])
                if not isfinite(atr) or atr <= 0:
                    continue
                lo, hi = float(row[low_col]), float(row[high_col])
                rc, ro = float(row[close_col]), float(row[open_col])
                tolerance = max(atr * cls.RETEST_ATR_TOLERANCE, level * 0.0001)
                touched = lo <= level + tolerance if direction == "LONG" else hi >= level - tolerance
                held = rc >= level if direction == "LONG" else rc <= level
                aligned = rc > ro if direction == "LONG" else rc < ro
                intervening = frame[close_col].iloc[breakout_i + 1:retest_i]
                invalidated = (intervening < level).any() if direction == "LONG" else (intervening > level).any()
                if touched and held and aligned and not invalidated and retest_i == end:
                    return {
                        "level": level, "atr": atr, "retest_low": lo,
                        "retest_high": hi, "breakout_index": breakout_i,
                        "retest_index": retest_i, "volume_ratio": vol / avg_volume,
                    }, "15m Donchian breakout and retest confirmed"
        return None, "No fresh 15m breakout with a confirmed retest"

    @classmethod
    def _confirm_5m(cls, frame, direction, level):
        if frame is None or len(frame) < 3:
            return False, "Need at least 3 closed 5m candles"
        o, h, lo, c = [cls._series_value(frame, x) for x in ("open", "high", "low", "close")]
        prev_h = cls._series_value(frame, "high", -2)
        prev_l = cls._series_value(frame, "low", -2)
        if None in (o, h, lo, c, prev_h, prev_l):
            return False, "Missing 5m OHLC data"
        if direction == "LONG" and c > o and c > prev_h and c >= level:
            return True, "5m bullish close above prior high and breakout level"
        if direction == "SHORT" and c < o and c < prev_l and c <= level:
            return True, "5m bearish close below prior low and breakout level"
        return False, "Waiting for 5m directional follow-through"

    def analyze(self, market_data, market="futures"):
        market = str(market).strip().lower()
        if market not in ("spot", "futures"):
            return {"success": False, "reason": "market must be spot or futures"}
        regime, regime_reason = self._regime(market_data.get("1h"))
        if regime == "UNKNOWN" or regime == "RANGING":
            return {"success": False, "reason": regime_reason, "market_regime": regime}
        if market == "spot" and regime != "BULLISH":
            return {"success": False, "reason": "Spot BUY blocked outside bullish regime", "market_regime": regime}
        directions = ("LONG",) if market == "spot" else (("LONG",) if regime == "BULLISH" else ("SHORT",))
        direction = directions[0]
        retest, reason = self._find_retest(market_data.get("15m"), direction)
        if retest is None:
            return {"success": False, "reason": reason, "market_regime": regime}
        confirmed, confirmation = self._confirm_5m(market_data.get("5m"), direction, retest["level"])
        if not confirmed:
            return {"success": False, "reason": confirmation, "market_regime": regime}
        entry = self._series_value(market_data.get("5m"), "close")
        atr = retest["atr"]
        buffer = max(atr * self.STOP_ATR_BUFFER, entry * 0.0001)
        if direction == "LONG":
            stop = min(retest["retest_low"], retest["level"]) - buffer
            stop = min(stop, entry - self.MIN_STOP_ATR * atr)
        else:
            stop = max(retest["retest_high"], retest["level"]) + buffer
            stop = max(stop, entry + self.MIN_STOP_ATR * atr)
        risk = abs(entry - stop)
        target1 = entry + self.TARGET_R * risk if direction == "LONG" else entry - self.TARGET_R * risk
        fee = self.FEES[market]
        round_trip_cost = 2.0 * (fee + self.SLIPPAGE_RATE)
        gross_reward_pct = abs(target1 - entry) / entry
        gross_risk_pct = risk / entry
        net_reward_pct = gross_reward_pct - round_trip_cost
        net_risk_pct = gross_risk_pct + round_trip_cost
        net_rr = net_reward_pct / net_risk_pct if net_risk_pct > 0 else 0.0
        if net_reward_pct <= 0 or net_rr < self.MIN_NET_RR:
            return {"success": False, "reason": "2R target does not provide 1.5 net R/R after estimated costs",
                    "net_reward_risk": round(net_rr, 3), "market_regime": regime}
        return {
            "success": True, "symbol": str(market_data.get("symbol", "")).upper(),
            "market": market, "direction": direction, "entry": entry,
            "stop_loss": stop, "take_profit": target1, "take_profit_2": None,
            "tp1_close_pct": 30, "trailing_after_tp1": True,
            "atr": atr, "risk_distance": risk, "reward_risk": self.TARGET_R,
            "net_reward_risk": round(net_rr, 3), "market_regime": regime,
            "regime_reason": regime_reason, "entry_confirmation": confirmation,
            "breakout": retest, "strategy": "adaptive_donchian_breakout_retest_v1",
        }

    @staticmethod
    def size_position(equity, entry, stop, risk_fraction=0.0025, max_notional_multiple=1.0):
        """Return quantity from cash risk; leverage is not used to inflate risk."""
        values = (float(equity), float(entry), float(stop), float(risk_fraction), float(max_notional_multiple))
        if not all(isfinite(v) for v in values) or equity <= 0 or entry <= 0 or stop <= 0:
            return 0.0
        if not 0 < risk_fraction <= 0.01 or max_notional_multiple <= 0:
            return 0.0
        per_unit = abs(entry - stop)
        if per_unit <= 0:
            return 0.0
        return min(equity * risk_fraction / per_unit,
                   equity * max_notional_multiple / entry)

    @staticmethod
    def update_trailing_stop(direction, current_stop, best_price, atr, multiplier=3.0):
        """Chandelier-style stop; it may tighten but must never loosen."""
        values = (float(current_stop), float(best_price), float(atr), float(multiplier))
        if not all(isfinite(v) for v in values) or atr <= 0 or multiplier <= 0:
            return current_stop
        direction = str(direction).upper()
        candidate = best_price - multiplier * atr if direction == "LONG" else best_price + multiplier * atr
        if direction == "LONG":
            return max(current_stop, candidate)
        if direction == "SHORT":
            return min(current_stop, candidate)
        raise ValueError("direction must be LONG or SHORT")
