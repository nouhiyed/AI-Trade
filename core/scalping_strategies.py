"""Separate research-only 5m scalping playbooks for Binance Spot and USD-M Futures."""
from math import isfinite


class _BaseScalper:
    FEE_RATE = {"spot": 0.0010, "futures": 0.0005}
    MIN_NET_REWARD_RATE = 0.0003
    MIN_NET_RR = 0.15

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

    @staticmethod
    def volume_ratio(frame, lookback=20):
        if frame is None or len(frame) < lookback + 1 or "volume" not in frame.columns:
            return 1.0
        try:
            avg = float(frame["volume"].iloc[-lookback-1:-1].astype(float).mean())
            return float(frame["volume"].iloc[-1]) / avg if avg > 0 else 1.0
        except (TypeError, ValueError):
            return 1.0

    @classmethod
    def plan(cls, market, direction, frame, setup, regime, target_r, costs):
        entry, atr = cls.value(frame, "close"), cls.value(frame, "ATR")
        if entry is None or atr is None or entry <= 0 or atr <= 0:
            return {"success": False, "reason": "Missing valid 5m close or ATR"}
        distance = max(1.15 * atr, entry * 0.0008)
        stop = entry - distance if direction == "LONG" else entry + distance
        target = entry + target_r * distance if direction == "LONG" else entry - target_r * distance
        fee = cls.FEE_RATE[market]
        adverse = max(0.0, float((costs or {}).get("total_adverse_rate", 0.0002)))
        round_trip = 2.0 * (fee + adverse)
        net_reward = abs(target - entry) / entry - round_trip
        net_risk = distance / entry + round_trip
        net_rr = net_reward / net_risk if net_risk > 0 else 0.0
        if net_reward < cls.MIN_NET_REWARD_RATE or net_rr < cls.MIN_NET_RR:
            return {"success": False, "reason": "Expected move does not clear estimated round-trip costs",
                    "estimated_net_reward_rate": net_reward, "net_reward_risk": net_rr}
        return {"success": True, "market": market, "direction": direction, "entry": entry,
                "stop_loss": stop, "take_profit": target, "atr": atr, "risk_distance": distance,
                "reward_risk": target_r, "net_reward_risk": round(net_rr, 4), "setup": setup,
                "market_regime": regime, "estimated_round_trip_cost_rate": round_trip,
                "estimated_net_reward_rate": net_reward,
                "strategy": "futures_momentum_range_scalper_v1" if market == "futures" else "spot_long_scalper_v1"}


class FuturesScalpingStrategy(_BaseScalper):
    """Trend pullback/breakout and low-ADX range reversal; long and short."""
    TARGET_R = 1.9
    MAX_HOLD_MINUTES = 24

    def analyze(self, data, costs=None):
        five, fifteen, hourly = data.get("5m"), data.get("15m"), data.get("1h")
        if any(x is None or len(x) < 30 for x in (five, fifteen, hourly)):
            return {"success": False, "reason": "Need closed 5m, 15m and 1h candles"}
        v = self.value
        c, o, h, lo = (v(five, x) for x in ("close", "open", "high", "low"))
        e9, e21, atr, rsi = (v(five, x) for x in ("EMA_9", "EMA_21", "ATR", "RSI"))
        hist, prev_hist = v(five, "MACD_hist"), v(five, "MACD_hist", -2)
        bb_lo, bb_hi = v(five, "BB_lower"), v(five, "BB_upper")
        adx, c15, e21_15, e50_15 = (v(fifteen, x) for x in ("ADX", "close", "EMA_21", "EMA_50"))
        c1h, e200_1h = v(hourly, "close"), v(hourly, "EMA_200")
        if any(x is None for x in (c,o,h,lo,e9,e21,atr,rsi,hist,prev_hist,adx,c15,e21_15,e50_15,c1h,e200_1h)) or atr <= 0:
            return {"success": False, "reason": "Missing scalping indicators"}
        bull = c15 > e50_15 and e21_15 > e50_15 and c1h >= e200_1h * 0.995
        bear = c15 < e50_15 and e21_15 < e50_15 and c1h <= e200_1h * 1.005
        vr = self.volume_ratio(five)
        prior_high, prior_low = float(five["high"].iloc[-13:-1].max()), float(five["low"].iloc[-13:-1].min())
        lp = bull and lo <= e21 + .20*atr and c > e9 and c > o and 42 <= rsi <= 70 and hist >= prev_hist
        sp = bear and h >= e21 - .20*atr and c < e9 and c < o and 30 <= rsi <= 58 and hist <= prev_hist
        lb = bull and c > prior_high and c > o and rsi < 76 and vr >= 1.05
        sb = bear and c < prior_low and c < o and rsi > 24 and vr >= 1.05
        if lp or lb:
            return self.plan("futures", "LONG", five, "TREND_PULLBACK" if lp else "MOMENTUM_BREAKOUT", "BULL_TREND", self.TARGET_R, costs)
        if sp or sb:
            return self.plan("futures", "SHORT", five, "TREND_PULLBACK" if sp else "MOMENTUM_BREAKOUT", "BEAR_TREND", self.TARGET_R, costs)
        if adx <= 19 and bb_lo is not None and bb_hi is not None:
            if rsi <= 29 and c <= bb_lo*1.002 and c > o:
                return self.plan("futures", "LONG", five, "RANGE_MEAN_REVERSION", "RANGE", self.TARGET_R, costs)
            if rsi >= 71 and c >= bb_hi*.998 and c < o:
                return self.plan("futures", "SHORT", five, "RANGE_MEAN_REVERSION", "RANGE", self.TARGET_R, costs)
        return {"success": False, "reason": "No qualifying futures scalp setup"}


class SpotScalpingStrategy(_BaseScalper):
    """Long-only: bullish pullback/breakout and oversold range bounce."""
    TARGET_R = 2.4
    MAX_HOLD_MINUTES = 36

    def analyze(self, data, costs=None):
        five, fifteen, hourly = data.get("5m"), data.get("15m"), data.get("1h")
        if any(x is None or len(x) < 30 for x in (five, fifteen, hourly)):
            return {"success": False, "reason": "Need closed 5m, 15m and 1h candles"}
        v = self.value
        c, o, h, lo = (v(five, x) for x in ("close", "open", "high", "low"))
        e9, e21, atr, rsi = (v(five, x) for x in ("EMA_9", "EMA_21", "ATR", "RSI"))
        hist, prev_hist = v(five, "MACD_hist"), v(five, "MACD_hist", -2)
        bb_lo = v(five, "BB_lower")
        adx, c15, e21_15, e50_15 = (v(fifteen, x) for x in ("ADX", "close", "EMA_21", "EMA_50"))
        c1h, e200_1h = v(hourly, "close"), v(hourly, "EMA_200")
        if any(x is None for x in (c,o,h,lo,e9,e21,atr,rsi,hist,prev_hist,adx,c15,e21_15,e50_15,c1h,e200_1h)) or atr <= 0:
            return {"success": False, "reason": "Missing spot scalping indicators"}
        four = data.get("4h")
        if four is not None and len(four) >= 30:
            c4, e200_4 = v(four, "close"), v(four, "EMA_200")
            if c4 is not None and e200_4 is not None and c4 < e200_4*.985:
                return {"success": False, "reason": "4h trend filter blocks spot long"}
        bullish = c15 > e50_15 and e21_15 > e50_15 and c1h >= e200_1h*.995
        vr = self.volume_ratio(five)
        prior_high = float(five["high"].iloc[-13:-1].max())
        pullback = bullish and lo <= e21+.20*atr and c > e9 and c > o and 40 <= rsi <= 68 and hist >= prev_hist
        breakout = bullish and c > prior_high and c > o and rsi < 74 and vr >= 1.05
        if pullback or breakout:
            return self.plan("spot", "LONG", five, "BULL_PULLBACK" if pullback else "BULL_BREAKOUT", "BULL_TREND", self.TARGET_R, costs)
        if adx <= 18 and bb_lo is not None and rsi <= 26 and c <= bb_lo*1.002 and c > o:
            return self.plan("spot", "LONG", five, "RANGE_OVERSOLD_BOUNCE", "RANGE", self.TARGET_R, costs)
        return {"success": False, "reason": "No qualifying spot long setup"}
