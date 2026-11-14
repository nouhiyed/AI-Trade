"""The sole live strategy: V3 1m trigger with closed higher-timeframe context.\nThis module is the only strategy path used by Futures and Spot agents.

No legacy strategy fallback is permitted. Every accepted plan must clear 1.5
net reward/risk after the configured round-trip fee and adverse-cost estimate.
"""
from math import isfinite


class _V3Base:
    STOP_ATR = 0.90
    MIN_NET_RR = 1.5
    MIN_NET_REWARD_RATE = 0.00035
    FEE_RATE = {"spot": 0.0010, "futures": 0.0005}
    ADVERSE_RATE = 0.0005

    @staticmethod
    def value(frame, name, index=-1):
        if frame is None or not hasattr(frame, "columns") or len(frame) < abs(index):
            return None
        cols = {str(c).strip().lower(): c for c in frame.columns}
        col = cols.get(name.lower())
        if col is None:
            return None
        try:
            value = float(frame[col].iloc[index])
            return value if isfinite(value) else None
        except (TypeError, ValueError, IndexError, KeyError):
            return None

    @classmethod
    def volume_ratio(cls, frame, lookback=30):
        if frame is None or len(frame) < lookback + 1 or "volume" not in frame.columns:
            return 1.0
        try:
            avg = float(frame["volume"].iloc[-lookback-1:-1].astype(float).mean())
            return float(frame["volume"].iloc[-1]) / avg if avg > 0 else 1.0
        except (TypeError, ValueError):
            return 1.0

    @classmethod
    def bias(cls, five, fifteen, direction):
        c5, e21_5 = cls.value(five, "close"), cls.value(five, "EMA_21")
        c15, e21_15, e50_15 = (cls.value(fifteen, x) for x in ("close", "EMA_21", "EMA_50"))
        if None in (c5, e21_5, c15, e21_15, e50_15):
            return False
        if direction == "LONG":
            return c15 > e50_15 and (c5 >= e21_5 or e21_15 > e50_15)
        return c15 < e50_15 and (c5 <= e21_5 or e21_15 < e50_15)

    @classmethod
    def plan(cls, market, direction, five, setup, regime, base_target_r, current_price):
        atr = cls.value(five, "ATR")
        entry = current_price
        if entry is None or atr is None or entry <= 0 or atr <= 0:
            return {"success": False, "reason": "V3 cannot build a valid entry/ATR plan"}
        distance = max(cls.STOP_ATR * atr, entry * 0.0008)
        fee = cls.FEE_RATE[market]
        round_trip = 2.0 * (fee + cls.ADVERSE_RATE)
        risk_rate = distance / entry
        # Solve (target*R - round-trip)/(risk + round-trip) >= 1.5.
        required_target_r = cls.MIN_NET_RR + (1.0 + cls.MIN_NET_RR) * round_trip / risk_rate
        target_r = max(float(base_target_r), required_target_r)
        stop = entry - distance if direction == "LONG" else entry + distance
        target = entry + target_r * distance if direction == "LONG" else entry - target_r * distance
        if not isfinite(stop) or not isfinite(target) or stop <= 0 or target <= 0:
            return {"success": False, "reason": "V3 calculated non-positive stop or target"}
        if direction == "LONG" and not stop < entry < target:
            return {"success": False, "reason": "V3 LONG stop/target geometry is invalid"}
        if direction == "SHORT" and not target < entry < stop:
            return {"success": False, "reason": "V3 SHORT stop/target geometry is invalid"}
        net_reward = target_r * risk_rate - round_trip
        net_risk = risk_rate + round_trip
        net_rr = net_reward / net_risk if net_risk > 0 else 0.0
        if net_reward < cls.MIN_NET_REWARD_RATE or net_rr + 1e-9 < cls.MIN_NET_RR:
            return {"success": False, "reason": "V3 plan fails the 1.5 net RR requirement",
                    "net_reward_risk": round(net_rr, 5)}
        return {
            "success": True, "market": market, "direction": direction,
            "entry": entry, "stop_loss": stop, "take_profit": target,
            "atr": atr, "risk_distance": distance, "reward_risk": target_r,
            "net_reward_risk": round(net_rr, 5), "setup": setup,
            "market_regime": regime, "estimated_round_trip_cost_rate": round_trip,
            "estimated_net_reward_rate": net_reward,
            "strategy": market + "_scalper_v3", "strategy_version": "v3",
            "stop_atr_multiple": cls.STOP_ATR, "timeframe": "1m",
            "max_hold_minutes": int(getattr(cls, "MAX_HOLD_MINUTES", 0)),
        }

    @classmethod
    def location(cls, frame):
        high, low, close = (cls.value(frame, x) for x in ("high", "low", "close"))
        return (close - low) / (high - low) if None not in (high, low, close) and high > low else 0.5


class FuturesScalpingStrategyV3(_V3Base):
    MAX_HOLD_MINUTES = 12

    def analyze(self, data, costs=None):
        one, five, fifteen = (data.get(x) for x in ("1m", "5m", "15m"))
        if any(x is None or len(x) < 30 for x in (one, five, fifteen)):
            return {"success": False, "reason": "V3 requires closed 1m, 5m and 15m candles"}
        v = self.value
        c, o, h, low, ema9, ema20, atr, rsi = (v(one, x) for x in
            ("close", "open", "high", "low", "EMA_9", "EMA_20", "ATR", "RSI"))
        hist, prev, adx5 = v(one, "MACD_hist"), v(one, "MACD_hist", -2), v(five, "ADX")
        if None in (c, o, h, low, ema9, ema20, atr, rsi, hist, prev, adx5) or atr <= 0:
            return {"success": False, "reason": "V3 Futures indicators are incomplete"}
        loc, body, vr = self.location(one), abs(c-o)/atr, self.volume_ratio(one)
        prior_high = float(one["high"].iloc[-11:-1].max())
        prior_low = float(one["low"].iloc[-11:-1].min())
        bull, bear = self.bias(five, fifteen, "LONG"), self.bias(five, fifteen, "SHORT")
        setups = [
            (bull and low <= ema20 + .18*atr and c > ema9 and c > o and 42 <= rsi <= 69
             and hist >= prev and loc >= .55 and body >= .08 and vr >= .72,
             "LONG", "MICRO_PULLBACK", "BULL_TREND", 1.35),
            (bear and h >= ema20 - .18*atr and c < ema9 and c < o and 31 <= rsi <= 58
             and hist <= prev and loc <= .45 and body >= .08 and vr >= .72,
             "SHORT", "MICRO_PULLBACK", "BEAR_TREND", 1.35),
            (bull and c > prior_high + .015*atr and c > o and 48 <= rsi <= 76
             and loc >= .62 and body >= .12 and vr >= .85,
             "LONG", "MICRO_BREAKOUT", "BULL_TREND", 1.45),
            (bear and c < prior_low - .015*atr and c < o and 24 <= rsi <= 52
             and loc <= .38 and body >= .12 and vr >= .85,
             "SHORT", "MICRO_BREAKOUT", "BEAR_TREND", 1.45),
        ]
        for valid, direction, setup, regime, target_r in setups:
            if valid:
                return self.plan("futures", direction, five, setup, regime, target_r, c)
        bb_low, bb_high = v(one, "BB_lower"), v(one, "BB_upper")
        if adx5 <= 20 and loc >= .62 and c > o and rsi <= 29 and bb_low and c <= bb_low*1.003:
            return self.plan("futures", "LONG", five, "RANGE_REJECTION", "RANGE", 1.25, c)
        if adx5 <= 20 and loc <= .38 and c < o and rsi >= 71 and bb_high and c >= bb_high*.997:
            return self.plan("futures", "SHORT", five, "RANGE_REJECTION", "RANGE", 1.25, c)
        return {"success": False, "reason": "No qualifying V3 Futures setup"}


class SpotScalpingStrategyV3(_V3Base):
    MAX_HOLD_MINUTES = 15

    def analyze(self, data, costs=None):
        one, five, fifteen, hourly, four = (data.get(x) for x in ("1m", "5m", "15m", "1h", "4h"))
        if any(x is None or len(x) < 30 for x in (one, five, fifteen, hourly)):
            return {"success": False, "reason": "V3 Spot requires closed 1m, 5m, 15m and 1h candles"}
        v = self.value
        c, o, h, low, ema9, ema20, atr, rsi = (v(one, x) for x in
            ("close", "open", "high", "low", "EMA_9", "EMA_20", "ATR", "RSI"))
        hist, prev = v(one, "MACD_hist"), v(one, "MACD_hist", -2)
        c1, e200 = v(hourly, "close"), v(hourly, "EMA_200")
        if None in (c, o, h, low, ema9, ema20, atr, rsi, hist, prev, c1, e200) or atr <= 0:
            return {"success": False, "reason": "V3 Spot indicators are incomplete"}
        if four is not None and len(four) >= 30:
            c4, e2004 = v(four, "close"), v(four, "EMA_200")
            if c4 is not None and e2004 and c4 < e2004*.975 and c1 < e200:
                return {"success": False, "reason": "Deep 4h and 1h bearish context"}
        loc, body, vr = self.location(one), abs(c-o)/atr, self.volume_ratio(one)
        prior_high = float(one["high"].iloc[-11:-1].max())
        c5, e21_5 = v(five, "close"), v(five, "EMA_21")
        bullish = self.bias(five, fifteen, "LONG") or (
            c1 > e200 and c5 is not None and e21_5 is not None and c5 >= e21_5
        )
        pull = (bullish and low <= ema20+.20*atr and c > ema9 and c > o and
                40 <= rsi <= 70 and hist >= prev and loc >= .54 and body >= .07 and vr >= .68)
        breakout = (bullish and c > prior_high+.01*atr and c > o and 48 <= rsi <= 76 and
                    loc >= .60 and body >= .11 and vr >= .82)
        if pull:
            return self.plan("spot", "LONG", five, "MICRO_PULLBACK", "BULL_TREND", 1.45, c)
        if breakout:
            return self.plan("spot", "LONG", five, "MICRO_BREAKOUT", "BULL_TREND", 1.55, c)
        adx5, bb = v(five, "ADX"), v(one, "BB_lower")
        if adx5 is not None and adx5 <= 19 and bb is not None and rsi <= 27 and c <= bb*1.004 and c > o and loc >= .60 and vr >= .65:
            return self.plan("spot", "LONG", five, "RANGE_BOUNCE", "RANGE", 1.35, c)
        return {"success": False, "reason": "No qualifying V3 Spot setup"}
