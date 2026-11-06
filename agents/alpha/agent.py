import pandas as pd
from agents.base_agent import BaseAgent


class AlphaAgent(BaseAgent):

    def __init__(self):
        super().__init__("Alpha-Agent", "alpha")
        self.execution_enabled = False

    def _flag(self, value):
        if value is None or pd.isna(value):
            return False
        if isinstance(value, str):
            return value.upper() in (
                "TRUE", "1", "BUY", "BULLISH"
            )
        return bool(value)

    def analyze(self, market_data):

        required = ["5m", "15m", "1h"]
        scores = {"BUY": 0, "AVOID": 0}
        details = {}

        symbol = market_data.get("symbol", "UNKNOWN")

        # Safety gate: fail closed

        safety = market_data.get("token_safety")

        safety_status = (
            safety.get("status", "UNKNOWN")
            if isinstance(safety, dict)
            else "UNKNOWN"
        )

        safety_critical = (
            safety_status.upper() in
            ("REJECT", "CRITICAL", "FAIL", "DANGER")
        )

        safety_passed = (
            safety_status.upper() == "PASS"
        )

        # Required timeframes

        for tf in required:

            if tf not in market_data:
                return self.record_signal({
                    "symbol": symbol,
                    "direction": "WAIT",
                    "confidence": 0,
                    "reason": f"Missing timeframe: {tf}",
                    "execution_enabled": False
                })

            df = market_data[tf]

            if len(df) < 60:
                return self.record_signal({
                    "symbol": symbol,
                    "direction": "WAIT",
                    "confidence": 0,
                    "reason": f"Insufficient candles: {tf}",
                    "execution_enabled": False
                })

            last = df.iloc[-1]

            fields = [
                "close", "RSI", "EMA_9", "EMA_21",
                "MACD", "MACD_signal", "ADX",
                "volume", "OBV"
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
            macd = float(last["MACD"])
            macd_signal = float(last["MACD_signal"])
            adx = float(last["ADX"])
            volume = float(last["volume"])
            obv = float(last["OBV"])

            avg_volume = float(
                df["volume"].tail(20).mean()
            )

            buy = 0
            avoid = 0

            # Momentum

            if close > ema9 > ema21:
                buy += 2

            if macd > macd_signal:
                buy += 1

            # RSI

            if 50 < rsi < 70:
                buy += 2
            elif rsi >= 80 or rsi <= 25:
                avoid += 2

            # Volume

            if avg_volume > 0:
                volume_ratio = volume / avg_volume

                if volume_ratio >= 1.5:
                    buy += 2

                if volume_ratio < 0.5:
                    avoid += 1
            else:
                volume_ratio = 0

            # Trend strength

            if adx >= 20:
                buy += 1

            # OBV

            if len(df) >= 6:
                previous_obv = float(df["OBV"].iloc[-6])

                if obv > previous_obv:
                    buy += 1
                elif obv < previous_obv:
                    avoid += 1

            # Market structure

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
                avoid += 1

            if smc["bearish_fvg"]:
                avoid += 0.5

            if smc["bearish_ob"]:
                avoid += 0.5

            # Bearish BOS and CHoCH

            if str(last.get("BOS", "")).upper() == "BEARISH":
                avoid += 2

            if str(last.get("CHoCH", "")).upper() == "BEARISH":
                avoid += 1

            scores["BUY"] += buy
            scores["AVOID"] += avoid

            details[tf] = {
                "rsi": round(rsi, 2),
                "adx": round(adx, 2),
                "volume_ratio": round(volume_ratio, 2),
                "buy_score": buy,
                "avoid_score": avoid,
                "smc": smc
            }

        # Order Book

        orderbook = market_data.get("orderbook", {})
        orderbook_used = False
        imbalance = None

        if isinstance(orderbook, dict):
            if orderbook.get("available") is True:
                try:
                    imbalance = float(orderbook["imbalance"])
                    spread_pct = float(orderbook["spread_percent"])

                    if spread_pct <= 0.001:
                        orderbook_used = True

                        if imbalance >= 0.20:
                            scores["BUY"] += 2
                        elif imbalance <= -0.20:
                            scores["AVOID"] += 2

                except (KeyError, TypeError, ValueError):
                    pass

        # Safety information

        safety_report = {
            "status": safety_status,
            "passed": safety_passed,
            "critical": safety_critical,
            "data_available": isinstance(safety, dict)
        }

        # Final decision

        total = scores["BUY"] + scores["AVOID"]

        if total == 0:
            confidence = 0
        else:
            confidence = round(
                scores["BUY"] / total * 100, 2
            )

        direction = "WAIT"

        if safety_critical:
            reason = "Token rejected by safety checks"

        elif not safety_passed:
            reason = "Safety verification missing or incomplete"

        elif scores["BUY"] >= 5 and confidence >= 70:
            direction = "BUY"
            reason = "Alpha momentum, volume and SMC confirmed"

        else:
            reason = "Insufficient alpha confirmation"

        return self.record_signal({
            "symbol": symbol,
            "direction": direction,
            "confidence": confidence,
            "scores": scores,
            "timeframes": details,
            "orderbook": {
                "used": orderbook_used,
                "imbalance": imbalance
            },
            "token_safety": safety_report,
            "reason": reason,
            "execution_enabled": False
        })

