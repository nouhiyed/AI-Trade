import pandas as pd
from agents.base_agent import BaseAgent


class FuturesAgent(BaseAgent):

    def __init__(self):
        super().__init__("Futures-Agent", "futures")

    def _signal(self, value, direction):
        if pd.isna(value):
            return False

        if isinstance(value, str):
            value = value.upper().strip()
            return value in (
                ["BULLISH", "BUY", "LONG", "TRUE", "1"]
                if direction == "LONG"
                else ["BEARISH", "SELL", "SHORT", "TRUE", "1"]
            )

        return bool(value)

    def analyze(self, market_data):

        required = ["1m", "5m", "15m", "1h"]

        for tf in required:
            if tf not in market_data:
                return self.record_signal({
                    "symbol": market_data.get("symbol", "UNKNOWN"),
                    "direction": "WAIT",
                    "confidence": 0,
                    "reason": f"Missing timeframe: {tf}"
                })

        scores = {"LONG": 0, "SHORT": 0}
        details = {}

        for tf in required:

            df = market_data[tf]

            if len(df) < 210:
                return self.record_signal({
                    "symbol": market_data.get("symbol", "UNKNOWN"),
                    "direction": "WAIT",
                    "confidence": 0,
                    "reason": f"Insufficient candles: {tf}"
                })

            last = df.iloc[-1]

            required_columns = [
                "close", "RSI", "EMA_9", "EMA_21",
                "EMA_50", "EMA_200", "MACD",
                "MACD_signal", "ADX"
            ]

            if any(
                col not in df.columns or pd.isna(last[col])
                for col in required_columns
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

            long_score = 0
            short_score = 0

            # Technical analysis

            if close > ema200:
                long_score += 2
            elif close < ema200:
                short_score += 2

            if ema9 > ema21 > ema50:
                long_score += 2
            elif ema9 < ema21 < ema50:
                short_score += 2

            if macd > macd_signal:
                long_score += 1
            elif macd < macd_signal:
                short_score += 1

            if 50 < rsi < 70:
                long_score += 1
            elif 30 < rsi < 50:
                short_score += 1

            if adx >= 20:
                if long_score > short_score:
                    long_score += 1
                elif short_score > long_score:
                    short_score += 1

            # Market structure / SMC

            smc_signals = {}

            bullish_bos = self._signal(
                last.get("BOS"), "LONG"
            )
            bearish_bos = self._signal(
                last.get("BOS"), "SHORT"
            )

            bullish_choch = self._signal(
                last.get("CHoCH"), "LONG"
            )
            bearish_choch = self._signal(
                last.get("CHoCH"), "SHORT"
            )

            if bullish_bos:
                long_score += 2
            elif bearish_bos:
                short_score += 2

            if bullish_choch:
                long_score += 1
            elif bearish_choch:
                short_score += 1

            if self._signal(last.get("Bullish_Sweep"), "LONG"):
                long_score += 1

            if self._signal(last.get("Bearish_Sweep"), "SHORT"):
                short_score += 1

            if self._signal(last.get("Bullish_FVG"), "LONG"):
                long_score += 0.5

            if self._signal(last.get("Bearish_FVG"), "SHORT"):
                short_score += 0.5

            if self._signal(last.get("Bullish_OB"), "LONG"):
                long_score += 0.5

            if self._signal(last.get("Bearish_OB"), "SHORT"):
                short_score += 0.5

            smc_signals = {
                "bullish_bos": bullish_bos,
                "bearish_bos": bearish_bos,
                "bullish_choch": bullish_choch,
                "bearish_choch": bearish_choch,
                "bullish_sweep": self._signal(last.get("Bullish_Sweep"), "LONG"),
                "bearish_sweep": self._signal(last.get("Bearish_Sweep"), "SHORT"),
                "bullish_fvg": self._signal(last.get("Bullish_FVG"), "LONG"),
                "bearish_fvg": self._signal(last.get("Bearish_FVG"), "SHORT"),
                "bullish_ob": self._signal(last.get("Bullish_OB"), "LONG"),
                "bearish_ob": self._signal(last.get("Bearish_OB"), "SHORT")
            }

            scores["LONG"] += long_score
            scores["SHORT"] += short_score

            details[tf] = {
                "long_score": long_score,
                "short_score": short_score,
                "rsi": round(rsi, 2),
                "adx": round(adx, 2),
                "ema_bull_stack": ema9 > ema21 > ema50,
                "ema_bear_stack": ema9 < ema21 < ema50,
                "price_above_ema200": close > ema200,
                "macd_bullish": macd > macd_signal,
                "macd_bearish": macd < macd_signal,
                "rsi_bullish_zone": 50 < rsi < 70,
                "rsi_bearish_zone": 30 < rsi < 50,
                "smc": smc_signals
            }

        # Order Book analysis

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
                        scores["LONG"] += 2
                    elif imbalance <= -0.15:
                        scores["SHORT"] += 2

            except (KeyError, TypeError, ValueError):
                pass

        # Final decision

        total = scores["LONG"] + scores["SHORT"]

        if total == 0:
            direction = "WAIT"
            confidence = 0

        else:
            difference = abs(
                scores["LONG"] - scores["SHORT"]
            )

            confidence = round(
                difference / total * 100, 2
            )

            if scores["LONG"] > scores["SHORT"]:
                direction = "LONG"
            elif scores["SHORT"] > scores["LONG"]:
                direction = "SHORT"
            else:
                direction = "WAIT"

            if confidence < 25:
                direction = "WAIT"

        if direction == "WAIT":
            if total == 0:
                reason = "No directional evidence: LONG and SHORT scores are both zero"
            elif scores["LONG"] == scores["SHORT"]:
                reason = "Directional scores are balanced"
            else:
                reason = (
                    f"Directional confidence {confidence:.2f}% is below "
                    "the 25% decision threshold"
                )
        else:
            reason = "Technical + SMC + Order Book analysis"

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

