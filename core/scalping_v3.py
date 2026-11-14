"""Higher-frequency 1m-trigger scalping with 5m/15m context.

Research candidate only. Signals use closed 1m candles; execution remains next 1m open.
"""
from core.scalping_strategies import _BaseScalper


class _ScalperV3(_BaseScalper):
    STOP_ATR = 0.90
    MIN_NET_REWARD_RATE = 0.00035
    MIN_NET_RR = 0.22

    @staticmethod
    def _v(frame, name, index=-1):
        return _BaseScalper.value(frame, name, index)

    @staticmethod
    def _loc(frame):
        h, l, c = (_BaseScalper.value(frame, x) for x in ("high", "low", "close"))
        return (c-l)/(h-l) if None not in (h,l,c) and h > l else 0.5

    @staticmethod
    def _slope(frame, name, periods=3):
        now = _BaseScalper.value(frame, name)
        old = _BaseScalper.value(frame, name, -periods)
        return (now-old)/abs(old) if now is not None and old not in (None,0) else 0.0

    @classmethod
    def _bias(cls, five, fifteen, direction):
        c5, e21_5 = cls._v(five,"close"), cls._v(five,"EMA_21")
        c15, e21_15, e50_15 = (cls._v(fifteen,x) for x in ("close","EMA_21","EMA_50"))
        if None in (c5,e21_5,c15,e21_15,e50_15):
            return False
        if direction == "LONG":
            return (c15 > e50_15 and (c5 >= e21_5 or e21_15 > e50_15))
        return (c15 < e50_15 and (c5 <= e21_5 or e21_15 < e50_15))

    @classmethod
    def _plan(cls, market, direction, five, setup, regime, target_r, costs, current_price):
        risk_frame = five.copy()
        risk_frame.loc[risk_frame.index[-1], "close"] = current_price
        result = cls.plan(market,direction,risk_frame,setup,regime,target_r,costs)
        if result.get("success"):
            result.update(strategy=("futures_scalper_v3" if market=="futures" else "spot_scalper_v3"),
                          strategy_version="v3", stop_atr_multiple=cls.STOP_ATR)
        return result


class FuturesScalpingStrategyV3(_ScalperV3):
    MAX_HOLD_MINUTES = 12

    def analyze(self, data, costs=None):
        one, five, fifteen = data.get("1m"),data.get("5m"),data.get("15m")
        if any(x is None or len(x)<30 for x in (one,five,fifteen)):
            return {"success":False,"reason":"Need closed 1m, 5m and 15m candles"}
        v=self._v
        c,o,h,l,ema9,ema20,atr,rsi = (v(one,x) for x in ("close","open","high","low","EMA_9","EMA_20","ATR","RSI"))
        hist,prev,adx5=(v(one,"MACD_hist"),v(one,"MACD_hist",-2),v(five,"ADX"))
        if None in (c,o,h,l,ema9,ema20,atr,rsi,hist,prev,adx5) or atr<=0:
            return {"success":False,"reason":"Missing v3 1m indicators"}
        loc=self._loc(one); body=abs(c-o)/atr; vr=self.volume_ratio(one,30)
        prior_high=float(one["high"].iloc[-11:-1].max())
        prior_low=float(one["low"].iloc[-11:-1].min())
        bull=self._bias(five,fifteen,"LONG")
        bear=self._bias(five,fifteen,"SHORT")
        long_pull=(bull and l<=ema20+0.18*atr and c>ema9 and c>o
                   and 42<=rsi<=69 and hist>=prev and loc>=0.55 and body>=0.08 and vr>=0.72)
        short_pull=(bear and h>=ema20-0.18*atr and c<ema9 and c<o
                    and 31<=rsi<=58 and hist<=prev and loc<=0.45 and body>=0.08 and vr>=0.72)
        long_break=(bull and c>prior_high+0.015*atr and c>o and 48<=rsi<=76
                    and loc>=0.62 and body>=0.12 and vr>=0.85)
        short_break=(bear and c<prior_low-0.015*atr and c<o and 24<=rsi<=52
                     and loc<=0.38 and body>=0.12 and vr>=0.85)
        if long_pull:
            return self._plan("futures","LONG",five,"MICRO_PULLBACK","BULL_TREND",1.35,costs,c)
        if short_pull:
            return self._plan("futures","SHORT",five,"MICRO_PULLBACK","BEAR_TREND",1.35,costs)
        if long_break:
            return self._plan("futures","LONG",five,"MICRO_BREAKOUT","BULL_TREND",1.45,costs,c)
        if short_break:
            return self._plan("futures","SHORT",five,"MICRO_BREAKOUT","BEAR_TREND",1.45,costs)
        # Counter-trend trades are limited to clear 1m rejection in a weak 5m range.
        if adx5<=20 and loc>=0.62 and c>o and rsi<=29 and c<=v(one,"BB_lower")*1.003:
            return self._plan("futures","LONG",five,"RANGE_REJECTION","RANGE",1.25,costs,c)
        if adx5<=20 and loc<=0.38 and c<o and rsi>=71 and c>=v(one,"BB_upper")*0.997:
            return self._plan("futures","SHORT",five,"RANGE_REJECTION","RANGE",1.25,costs)
        return {"success":False,"reason":"No qualifying v3 micro setup"}


class SpotScalpingStrategyV3(_ScalperV3):
    MAX_HOLD_MINUTES = 15

    def analyze(self,data,costs=None):
        one,five,fifteen,hourly,four=(data.get(x) for x in ("1m","5m","15m","1h","4h"))
        if any(x is None or len(x)<30 for x in (one,five,fifteen,hourly)):
            return {"success":False,"reason":"Need closed 1m, 5m, 15m and 1h candles"}
        v=self._v
        c,o,h,l,ema9,ema20,atr,rsi=(v(one,x) for x in ("close","open","high","low","EMA_9","EMA_20","ATR","RSI"))
        hist,prev=(v(one,"MACD_hist"),v(one,"MACD_hist",-2))
        if None in (c,o,h,l,ema9,ema20,atr,rsi,hist,prev) or atr<=0:
            return {"success":False,"reason":"Missing v3 spot indicators"}
        c1,e200=(v(hourly,x) for x in ("close","EMA_200"))
        if None in (c1,e200):
            return {"success":False,"reason":"Missing 1h spot context"}
        # Soft 4h guard: avoid only deep bearish structure, not every sub-EMA pullback.
        if four is not None and len(four)>=30:
            c4,e2004=(v(four,x) for x in ("close","EMA_200"))
            if c4 is not None and e2004 and c4<e2004*0.975 and c1<e200:
                return {"success":False,"reason":"Deep 4h and 1h bearish context"}
        loc=self._loc(one); body=abs(c-o)/atr; vr=self.volume_ratio(one,30)
        prior_high=float(one["high"].iloc[-11:-1].max())
        bullish=self._bias(five,fifteen,"LONG") or (c1>e200 and v(five,"close")>=v(five,"EMA_21"))
        pull=(bullish and l<=ema20+0.20*atr and c>ema9 and c>o
              and 40<=rsi<=70 and hist>=prev and loc>=0.54 and body>=0.07 and vr>=0.68)
        breakout=(bullish and c>prior_high+0.01*atr and c>o and 48<=rsi<=76
                  and loc>=0.60 and body>=0.11 and vr>=0.82)
        if pull:
            return self._plan("spot","LONG",five,"MICRO_PULLBACK","BULL_TREND",1.45,costs)
        if breakout:
            return self._plan("spot","LONG",five,"MICRO_BREAKOUT","BULL_TREND",1.55,costs,c)
        adx5=v(five,"ADX"); bb=v(one,"BB_lower")
        if adx5 is not None and adx5<=19 and bb is not None and rsi<=27 and c<=bb*1.004 and c>o and loc>=0.60 and vr>=0.65:
            return self._plan("spot","LONG",five,"RANGE_BOUNCE","RANGE",1.35,costs)
        return {"success":False,"reason":"No qualifying v3 spot micro setup"}
