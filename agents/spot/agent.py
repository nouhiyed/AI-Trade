import pandas as pd
from agents.base_agent import BaseAgent


class SpotAgent(BaseAgent):

    def __init__(self):
        super().__init__("Spot-Agent", "spot")

    def _flag(self, value):
        if value is None or pd.isna(value):
            return False
        if isinstance(value, str):
            return value.upper() in ("TRUE", "1", "BUY", "BULLISH")
        return bool(value)

    def analyze(self, market_data):

        required = ["5m", "15m", "1h", "4h"]
        scores = {"BUY": 0, "SELL": 0}
        details = {}

        for tf in required:

            if tf not in market_data:
                return self.record_signal({
                    "symbol": market_data.get("symbol", "UNKNOWN"),
                    "direction": "WAIT",
                    "confidence": 0,
                    "reason": f"Missing timeframe: {tf}"
                })

            df = market_data[tf]

            if len(df) < 210:
                return self.record_signal({
                    "symbol": market_data.get("symbol", "UNKNOWN"),
                    "direction": "WAIT",
                    "confidence": 0,
                    "reason": f"Insufficient candles: {tf}"
                })

            last = df.iloc[-1]

            fields = [
                "close", "RSI", "EMA_9", "EMA_21",
                "EMA_50", "EMA_200",
                "MACD", "MACD_signal", "ADX"
            ]

            if any(
                field not in df.columns or pd.isna(last[field])
                for field in fields
            ):
                continue

            close = float(last["close"])
            rsi = float(last["RSI"])
            ema9 = float(last["EMA_9"])
            ema21 = float(last["EMA_21"])
            ema50 = float(last["EMA_50"])
            ema200 = float(last["EMA_200"])
            macd = float(last["MACD"])
            macd_signal = float(last["MACD_signal"])
            adx = float(last["ADX"])

            buy = 0
            sell = 0

            # Technical analysis

            if close > ema200:
                buy += 2
            elif close < ema200:
                sell += 2

            if ema9 > ema21 > ema50:
                buy += 2
            elif ema9 < ema21 < ema50:
                sell += 2

            if macd > macd_signal:
                buy += 1
            elif macd < macd_signal:
                sell += 1

            if 50 < rsi < 70:
                buy += 1
            elif 30 < rsi < 50:
                sell += 1

            if adx >= 20:
                if buy > sell:
                    buy += 1
                elif sell > buy:
                    sell += 1

            # SMC analysis

            smc = {
                "bullish_bos": self._flag(last.get("BOS")),
                "bullish_choch": self._flag(last.get("CHoCH")),
                "bullish_sweep": self._flag(last.get("Bullish_Sweep")),
                "bearish_sweep": self._flag(last.get("Bearish_Sweep")),
                "bullish_fvg": self._flag(last.get("Bullish_FVG")),
                "bearish_fvg": self._flag(last.get("Bearish_FVG")),
                "bullish_ob": self._flag(last.get("Bullish_OB")),
                "bearish_ob": self._flag(last.get("Bearish_OB"))
            }

            if smc["bullish_bos"]:
                buy += 2
            if smc["bullish_choch"]:
                buy += 1
            if smc["bullish_sweep"]:
                buy += 1
            if smc["bullish_fvg"]:
                buy += 0.5
            if smc["bullish_ob"]:
                buy += 0.5

            if smc["bearish_sweep"]:
                sell += 1
            if smc["bearish_fvg"]:
                sell += 0.5
            if smc["bearish_ob"]:
                sell += 0.5

            # Market structure bearish signals

            bearish_bos = (
                str(last.get("BOS", "")).upper() == "BEARISH"
            )
            bearish_choch = (
                str(last.get("CHoCH", "")).upper() == "BEARISH"
            )

            if bearish_bos:
                sell += 2
            if bearish_choch:
                sell += 1

            scores["BUY"] += buy
            scores["SELL"] += sell

            details[tf] = {
                "buy_score": buy,
                "sell_score": sell,
                "rsi": round(rsi, 2),
                "adx": round(adx, 2),
                "smc": smc
            }

        # Order Book

        orderbook = market_data.get("orderbook", {})
        orderbook_used = False
        imbalance = None

        if orderbook.get("available") is True:
            try:
                imbalance = float(orderbook["imbalance"])
                spread_pct = float(orderbook["spread_percent"])

                if spread_pct <= 0.001:
                    orderbook_used = True

                    if imbalance >= 0.15:
                        scores["BUY"] += 2
                    elif imbalance <= -0.15:
                        scores["SELL"] += 2

            except (KeyError, TypeError, ValueError):
                pass

        # Final decision

        total = scores["BUY"] + scores["SELL"]

        if total == 0:
            direction = "WAIT"
            confidence = 0
        else:
            difference = abs(scores["BUY"] - scores["SELL"])
            confidence = round(difference / total * 100, 2)

            if scores["BUY"] > scores["SELL"]:
                direction = "BUY"
            elif scores["SELL"] > scores["BUY"]:
                direction = "SELL"
            else:
                direction = "WAIT"

            if confidence < 25:
                direction = "WAIT"

        if direction == "WAIT":
            if total == 0:
                reason = "No valid BUY or SELL evidence across the required timeframes"
            elif scores["BUY"] == scores["SELL"]:
                reason = "BUY and SELL scores are balanced"
            else:
                reason = (
                    f"Directional confidence {confidence:.2f}% is below "
                    "the 25% decision threshold"
                )
        else:
            reason = "Spot technical + SMC + Order Book analysis"

        return self.record_signal({
            "symbol": market_data.get("symbol", "UNKNOWN"),
            "direction": direction,
            "confidence": confidence,
            "scores": scores,
            "timeframes": details,
            "orderbook": {
                "used": orderbook_used,
                "imbalance": imbalance
            },
            "reason": reason
        })

