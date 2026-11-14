"""Second-generation scalping filters, isolated from the v1 research baseline."""
from core.scalping_strategies import _BaseScalper


class _ScalperV2(_BaseScalper):
    MIN_NET_REWARD_RATE = 0.00045
    MIN_NET_RR = 0.30
    STOP_ATR = 1.15

    @classmethod
    def plan(cls, market, direction, frame, setup, regime, target_r, costs):
        result = super().plan(market, direction, frame, setup, regime, target_r, costs)
        if result.get("success"):
            result["strategy"] = (
                "futures_scalper_v2" if market == "futures" else "spot_scalper_v2"
            )
            result["strategy_version"] = "v2"
            result["stop_atr_multiple"] = cls.STOP_ATR
        return result

    @staticmethod
    def _close_location(frame):
        high = _ScalperV2.value(frame, "high")
        low = _ScalperV2.value(frame, "low")
        close = _ScalperV2.value(frame, "close")
        if None in (high, low, close) or high <= low:
            return 0.5
        return (close - low) / (high - low)

    @staticmethod
    def _body_atr(frame):
        op = _ScalperV2.value(frame, "open")
        close = _ScalperV2.value(frame, "close")
        atr = _ScalperV2.value(frame, "ATR")
        if None in (op, close, atr) or atr <= 0:
            return 0.0
        return abs(close - op) / atr

    @staticmethod
    def _slope(frame, name, periods=4):
        now = _ScalperV2.value(frame, name, -1)
        old = _ScalperV2.value(frame, name, -periods)
        if now is None or old is None or old == 0:
            return 0.0
        return (now - old) / abs(old)

    @classmethod
    def _trend(cls, fifteen, hourly, direction):
        c15 = cls.value(fifteen, "close")
        e21 = cls.value(fifteen, "EMA_21")
        e50 = cls.value(fifteen, "EMA_50")
        c1h = cls.value(hourly, "close")
        e200 = cls.value(hourly, "EMA_200")
        slope21 = cls._slope(fifteen, "EMA_21")
        slope200 = cls._slope(hourly, "EMA_200")
        if None in (c15, e21, e50, c1h, e200):
            return False
        if direction == "LONG":
            return c15 > e21 > e50 and c1h > e200 and slope21 > 0 and slope200 >= -0.0002
        return c15 < e21 < e50 and c1h < e200 and slope21 < 0 and slope200 <= 0.0002


class FuturesScalpingStrategyV2(_ScalperV2):
    TARGET_R = 1.60
    MAX_HOLD_MINUTES = 18

    def analyze(self, data, costs=None):
        five, fifteen, hourly = data.get("5m"), data.get("15m"), data.get("1h")
        if any(x is None or len(x) < 40 for x in (five, fifteen, hourly)):
            return {"success": False, "reason": "Need 40 closed candles on 5m, 15m and 1h"}
        v = self.value
        c, o, h, lo = (v(five, x) for x in ("close", "open", "high", "low"))
        e9, e21, atr, rsi = (v(five, x) for x in ("EMA_9", "EMA_21", "ATR", "RSI"))
        hist, prev_hist = v(five, "MACD_hist"), v(five, "MACD_hist", -2)
        adx, bb_lo, bb_hi = v(five, "ADX"), v(five, "BB_lower"), v(five, "BB_upper")
        if None in (c, o, h, lo, e9, e21, atr, rsi, hist, prev_hist, adx) or atr <= 0:
            return {"success": False, "reason": "Missing v2 indicators"}
        vr = self.volume_ratio(five)
        location, body = self._close_location(five), self._body_atr(five)
        slope9, slope21 = self._slope(five, "EMA_9"), self._slope(five, "EMA_21")
        prior_high = float(five["high"].iloc[-13:-1].max())
        prior_low = float(five["low"].iloc[-13:-1].min())

        bull = self._trend(fifteen, hourly, "LONG") and e9 > e21 and slope9 > 0 and slope21 > 0
        bear = self._trend(fifteen, hourly, "SHORT") and e9 < e21 and slope9 < 0 and slope21 < 0

        long_pullback = (
            bull and lo <= e21 + 0.12 * atr and c > e9 and c > o
            and 48 <= rsi <= 66 and hist > 0 and hist > prev_hist
            and body >= 0.18 and location >= 0.68 and vr >= 1.10
        )
        short_pullback = (
            bear and h >= e21 - 0.12 * atr and c < e9 and c < o
            and 34 <= rsi <= 52 and hist < 0 and hist < prev_hist
            and body >= 0.18 and location <= 0.32 and vr >= 1.10
        )
        long_breakout = (
            bull and c > prior_high + 0.08 * atr and c > o
            and 53 <= rsi <= 73 and vr >= 1.35
            and body >= 0.35 and location >= 0.78
        )
        short_breakout = (
            bear and c < prior_low - 0.08 * atr and c < o
            and 27 <= rsi <= 47 and vr >= 1.35
            and body >= 0.35 and location <= 0.22
        )
        if long_pullback:
            return self.plan("futures", "LONG", five, "TREND_PULLBACK", "BULL_TREND", self.TARGET_R, costs)
        if short_pullback:
            return self.plan("futures", "SHORT", five, "TREND_PULLBACK", "BEAR_TREND", self.TARGET_R, costs)
        if long_breakout:
            return self.plan("futures", "LONG", five, "MOMENTUM_BREAKOUT", "BULL_TREND", self.TARGET_R, costs)
        if short_breakout:
            return self.plan("futures", "SHORT", five, "MOMENTUM_BREAKOUT", "BEAR_TREND", self.TARGET_R, costs)

        # Range entries are intentionally rarer and require a confirmed rejection.
        if adx <= 16 and bb_lo is not None and bb_hi is not None and vr >= 0.90:
            if rsi <= 24 and c <= bb_lo and c > o and location >= 0.65:
                return self.plan("futures", "LONG", five, "RANGE_MEAN_REVERSION", "RANGE", 1.35, costs)
            if rsi >= 76 and c >= bb_hi and c < o and location <= 0.35:
                return self.plan("futures", "SHORT", five, "RANGE_MEAN_REVERSION", "RANGE", 1.35, costs)
        return {"success": False, "reason": "No qualifying v2 futures setup"}


class SpotScalpingStrategyV2(_ScalperV2):
    TARGET_R = 1.90
    MAX_HOLD_MINUTES = 24

    def analyze(self, data, costs=None):
        five, fifteen, hourly = data.get("5m"), data.get("15m"), data.get("1h")
        four = data.get("4h")
        if any(x is None or len(x) < 40 for x in (five, fifteen, hourly, four)):
            return {"success": False, "reason": "Need 40 closed candles on 5m, 15m, 1h and 4h"}
        v = self.value
        c, o, h, lo = (v(five, x) for x in ("close", "open", "high", "low"))
        e9, e21, atr, rsi = (v(five, x) for x in ("EMA_9", "EMA_21", "ATR", "RSI"))
        hist, prev_hist = v(five, "MACD_hist"), v(five, "MACD_hist", -2)
        adx, bb_lo = v(five, "ADX"), v(five, "BB_lower")
        c4, e200_4 = v(four, "close"), v(four, "EMA_200")
        if None in (c, o, h, lo, e9, e21, atr, rsi, hist, prev_hist, adx, c4, e200_4) or atr <= 0:
            return {"success": False, "reason": "Missing v2 spot indicators"}
        if c4 <= e200_4 or self._slope(four, "EMA_200") < -0.0002:
            return {"success": False, "reason": "4h trend filter blocks spot long"}
        bullish = self._trend(fifteen, hourly, "LONG") and e9 > e21 and self._slope(five, "EMA_21") > 0
        vr = self.volume_ratio(five)
        location, body = self._close_location(five), self._body_atr(five)
        prior_high = float(five["high"].iloc[-13:-1].max())
        pullback = (
            bullish and lo <= e21 + 0.12 * atr and c > e9 and c > o
            and 47 <= rsi <= 65 and hist > 0 and hist > prev_hist
            and body >= 0.18 and location >= 0.68 and vr >= 1.10
        )
        breakout = (
            bullish and c > prior_high + 0.08 * atr and c > o
            and 53 <= rsi <= 72 and vr >= 1.35
            and body >= 0.35 and location >= 0.78
        )
        if pullback:
            return self.plan("spot", "LONG", five, "BULL_PULLBACK", "BULL_TREND", self.TARGET_R, costs)
        if breakout:
            return self.plan("spot", "LONG", five, "BULL_BREAKOUT", "BULL_TREND", self.TARGET_R, costs)
        if adx <= 15 and bb_lo is not None and rsi <= 23 and c <= bb_lo and c > o and location >= 0.68 and vr >= 0.90:
            return self.plan("spot", "LONG", five, "RANGE_OVERSOLD_BOUNCE", "RANGE", 1.45, costs)
        return {"success": False, "reason": "No qualifying v2 spot setup"}
