from agents.base_agent import BaseAgent
from core.scalping_v3 import SpotScalpingStrategyV3


class SpotAgent(BaseAgent):
    """Spot agent: V3 only, long-only."""

    def __init__(self):
        super().__init__("Spot-Agent", "spot")
        self.strategy = SpotScalpingStrategyV3()

    def analyze(self, market_data):
        plan = self.strategy.analyze(market_data)
        approved = plan.get("success") is True and str(plan.get("direction", "")).upper() == "LONG"
        signal = {
            "symbol": market_data.get("symbol", "UNKNOWN"),
            "direction": "BUY" if approved else "WAIT",
            "confidence": 75.0 if approved else 0.0,
            "reason": ("V3 " + str(plan.get("setup", "setup")) if approved
                       else plan.get("reason", "V3 did not produce an approved setup")),
            "strategy_tag": "v3_" + str(plan.get("setup", "no_setup")).lower(),
            "strategy_version": "v3",
            "trade_plan": plan if approved else plan,
            "scores": {"BUY": 1 if approved else 0, "SELL": 0},
            "timeframes": {"1m": {"strategy": "v3"}, "5m": {"strategy": "v3"},
                           "15m": {"strategy": "v3"}, "1h": {"strategy": "v3"},
                           "4h": {"strategy": "v3"}},
        }
        return self.record_signal(signal)
