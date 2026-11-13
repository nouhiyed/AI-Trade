"""Research-first multi-timeframe breakout/retest strategy; never executes orders."""
from math import isfinite

from core.market_regime import MarketRegimeEngine
from core.backtest_costs import BacktestCostModel


class AdaptiveTrendStrategy:
    """1h regime engine + 15m breakout/retest quality + 5m confirmation."""

    DONCHIAN_LOOKBACK = 20
    BREAKOUT_SEARCH_BARS = 10
    RETEST_SEARCH_BARS = 4
    MIN_VOLUME_RATIO = 1.10
    WEAK_TREND_VOLUME_RATIO = 1.25
    RETEST_ATR_TOLERANCE = 0.25
    MAX_RETEST_DEPTH_ATR = 0.50
    MIN_BREAKOUT_BODY_RATIO = 0.45
    MIN_BREAKOUT_CLOSE_LOCATION = 0.70
    MAX_BREAKOUT_EXTENSION_ATR = 1.25
    MAX_RETEST_VOLUME_RATIO = 0.90
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
        result = MarketRegimeEngine.classify(frame)
        return result["regime"], result["reason"], result

    @classmethod
    def _find_retest(cls, frame, direction, strength="STRONG"):
        minimum = cls.DONCHIAN_LOOKBACK + 8
        if frame is None or len(frame) < minimum:
            return None, "Not enough 15m candles"
        cols = {name: cls._column(frame, name) for name in
                ("high", "low", "close", "open", "volume", "ATR")}
        if any(value is None for value in cols.values()):
            return None, "15m OHLCV/ATR columns missing"
        high_col, low_col = cols["high"], cols["low"]
        close_col, open_col = cols["close"], cols["open"]
        volume_col, atr_col = cols["volume"], cols["ATR"]
        start = max(cls.DONCHIAN_LOOKBACK, len(frame) - cls.BREAKOUT_SEARCH_BARS - cls.RETEST_SEARCH_BARS - 1)
        end = len(frame) - 1
        min_volume = cls.WEAK_TREND_VOLUME_RATIO if strength == "WEAK" else cls.MIN_VOLUME_RATIO

        for breakout_i in range(end - 2, start - 1, -1):
            prior = frame.iloc[breakout_i - cls.DONCHIAN_LOOKBACK:breakout_i]
            level = float(prior[high_col].max() if direction == "LONG" else prior[low_col].min())
            candle = frame.iloc[breakout_i]
            hi, lo = float(candle[high_col]), float(candle[low_col])
            c, o = float(candle[close_col]), float(candle[open_col])
            atr = float(candle[atr_col])
            avg_volume = float(prior[volume_col].mean())
            vol = float(candle[volume_col])
            candle_range = hi - lo
            if (not isfinite(atr) or atr <= 0 or avg_volume <= 0 or candle_range <= 0
                    or vol < avg_volume * min_volume):
                continue
            broke = c > level if direction == "LONG" else c < level
            body_aligned = c > o if direction == "LONG" else c < o
            body_ratio = abs(c - o) / candle_range
            close_location = (c - lo) / candle_range
            if direction == "SHORT":
                close_location = 1.0 - close_location
            extension_atr = abs(c - level) / atr
            if not (broke and body_aligned and body_ratio >= cls.MIN_BREAKOUT_BODY_RATIO
                    and close_location >= cls.MIN_BREAKOUT_CLOSE_LOCATION
                    and extension_atr <= cls.MAX_BREAKOUT_EXTENSION_ATR):
                continue

            retest_start = breakout_i + 1
            retest_end = min(end, breakout_i + cls.RETEST_SEARCH_BARS)
            for retest_i in range(retest_end, retest_start - 1, -1):
                row = frame.iloc[retest_i]
                retest_atr = float(row[atr_col])
                if not isfinite(retest_atr) or retest_atr <= 0:
                    continue
                rlo, rhi = float(row[low_col]), float(row[high_col])
                rc, ro = float(row[close_col]), float(row[open_col])
                rrange = rhi - rlo
                if rrange <= 0:
                    continue
                tolerance = max(retest_atr * cls.RETEST_ATR_TOLERANCE, level * 0.0001)
                touched = rlo <= level + tolerance if direction == "LONG" else rhi >= level - tolerance
                held = rc >= level if direction == "LONG" else rc <= level
                aligned = rc > ro if direction == "LONG" else rc < ro
                rejection = ((rc - rlo) / rrange if direction == "LONG"
                             else (rhi - rc) / rrange)
                depth = (level - rlo if direction == "LONG" else rhi - level) / retest_atr
                retest_volume_ratio = float(row[volume_col]) / vol if vol > 0 else float("inf")
                intervening = frame[close_col].iloc[breakout_i + 1:retest_i]
                invalidated = ((intervening < level).any() if direction == "LONG"
                               else (intervening > level).any())
                if (touched and held and aligned and not invalidated and retest_i == end
                        and depth <= cls.MAX_RETEST_DEPTH_ATR
                        and rejection >= 0.60
                        and retest_volume_ratio <= cls.MAX_RETEST_VOLUME_RATIO):
                    return {
                        "level": level, "atr": retest_atr, "retest_low": rlo,
                        "retest_high": rhi, "breakout_index": breakout_i,
                        "retest_index": retest_i, "volume_ratio": vol / avg_volume,
                        "breakout_body_ratio": body_ratio,
                        "breakout_close_location": close_location,
                        "breakout_extension_atr": extension_atr,
                        "retest_depth_atr": depth,
                        "retest_rejection": rejection,
                        "retest_to_breakout_volume": retest_volume_ratio,
                    }, "Breakout/retest passed candle, extension, depth, rejection, and volume checks"
        return None, "No fresh high-quality 15m breakout/retest"

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
        regime, regime_reason, regime_data = self._regime(market_data.get("1h"))
        if not regime_data.get("allow_trade"):
            return {"success": False, "reason": regime_reason, "market_regime": regime,
                    "regime_details": regime_data}
        if market == "spot" and regime != "BULLISH":
            return {"success": False, "reason": "Spot BUY blocked outside bullish regime",
                    "market_regime": regime, "regime_details": regime_data}
        direction = "LONG" if regime == "BULLISH" else "SHORT"
        strength = regime_data.get("strength", "WEAK")
        retest, reason = self._find_retest(market_data.get("15m"), direction, strength)
        if retest is None:
            return {"success": False, "reason": reason, "market_regime": regime,
                    "regime_details": regime_data}
        confirmed, confirmation = self._confirm_5m(market_data.get("5m"), direction, retest["level"])
        if not confirmed:
            return {"success": False, "reason": confirmation, "market_regime": regime,
                    "regime_details": regime_data}
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
        execution_costs = BacktestCostModel(market).components(market_data.get("5m").iloc[-1])
        round_trip_cost = 2.0 * (fee + execution_costs["total_adverse_rate"])
        gross_reward_pct, gross_risk_pct = abs(target1 - entry) / entry, risk / entry
        net_reward_pct = gross_reward_pct - round_trip_cost
        net_risk_pct = gross_risk_pct + round_trip_cost
        net_rr = net_reward_pct / net_risk_pct if net_risk_pct > 0 else 0.0
        if net_reward_pct <= 0 or net_rr < self.MIN_NET_RR:
            return {"success": False, "reason": "Target does not provide 1.5 net R/R after estimated costs",
                    "net_reward_risk": round(net_rr, 3), "market_regime": regime,
                    "regime_details": regime_data}
        return {
            "success": True, "symbol": str(market_data.get("symbol", "")).upper(),
            "market": market, "direction": direction, "entry": entry,
            "stop_loss": stop, "take_profit": target1, "take_profit_2": None,
            "tp1_close_pct": 30, "trailing_after_tp1": True,
            "atr": atr, "risk_distance": risk, "reward_risk": self.TARGET_R,
            "net_reward_risk": round(net_rr, 3), "market_regime": regime,
            "regime_strength": strength, "regime_reason": regime_reason,
            "regime_details": regime_data, "entry_confirmation": confirmation,
            "breakout": retest, "execution_cost_estimate": execution_costs,
            "strategy": "adaptive_donchian_breakout_retest_v2",
        }

    @staticmethod
    def size_position(equity, entry, stop, risk_fraction=0.0025, max_notional_multiple=1.0):
        values = (float(equity), float(entry), float(stop), float(risk_fraction), float(max_notional_multiple))
        if not all(isfinite(v) for v in values) or equity <= 0 or entry <= 0 or stop <= 0:
            return 0.0
        if not 0 < risk_fraction <= 0.01 or max_notional_multiple <= 0:
            return 0.0
        per_unit = abs(entry - stop)
        if per_unit <= 0:
            return 0.0
        return min(equity * risk_fraction / per_unit, equity * max_notional_multiple / entry)

    @staticmethod
    def update_trailing_stop(direction, current_stop, best_price, atr, multiplier=3.0):
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
