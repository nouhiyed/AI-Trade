from abc import ABC, abstractmethod
from datetime import datetime, timezone


class BaseAgent(ABC):

    def __init__(self, name, domain):
        self.name = name
        self.domain = domain
        self.trades = []
        self.signals = []
        self.metrics = {
            "total_signals": 0,
            "total_trades": 0,
            "wins": 0,
            "losses": 0
        }

    @abstractmethod
    def analyze(self, market_data):
        pass

    def record_signal(self, signal):
        signal["agent"] = self.name
        signal["domain"] = self.domain
        signal["timestamp"] = datetime.now(
            timezone.utc
        ).isoformat()

        self.signals.append(signal)
        self.metrics["total_signals"] += 1

        return signal

    def record_trade(self, trade):
        self.trades.append(trade)
        self.metrics["total_trades"] += 1

        if trade.get("result") == "WIN":
            self.metrics["wins"] += 1
        elif trade.get("result") == "LOSS":
            self.metrics["losses"] += 1

    def get_performance(self):
        total = self.metrics["total_trades"]

        win_rate = (
            self.metrics["wins"] / total * 100
            if total else 0
        )

        return {
            **self.metrics,
            "win_rate": round(win_rate, 2)
        }

