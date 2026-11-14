from agents.base_agent import BaseAgent
from core.scalping_v3 import FuturesScalpingStrategyV3


class FuturesAgent(BaseAgent):
    """Futures agent: V3 only. LONG and SHORT are both supported."""

    def __init__(self):
        super().__init__("Futures-Agent", "futures")
        self.strategy = FuturesScalpingStrategyV3()

    def analyze(self, market_data):
        plan = self.strategy.analyze(market_data)
        direction = str(plan.get("direction", "WAIT")).upper() if plan.get("success") else "WAIT"
        signal = {
            "symbol": market_data.get("symbol", "UNKNOWN"),
            "direction": direction,
            "confidence": 75.0 if plan.get("success") else 0.0,
            "reason": ("V3 " + str(plan.get("setup", "setup")) if plan.get("success")
                       else plan.get("reason", "V3 did not produce an approved setup")),
            "strategy_tag": "v3_" + str(plan.get("setup", "no_setup")).lower(),
            "strategy_version": "v3",
            "trade_plan": plan,
            "scores": {"LONG": 1 if direction == "LONG" else 0,
                       "SHORT": 1 if direction == "SHORT" else 0},
            "timeframes": {"1m": {"strategy": "v3"}, "5m": {"strategy": "v3"},
                           "15m": {"strategy": "v3"}},
        }
        return self.record_signal(signal)
