"""Conservative learning from completed DEMO trades.

The first 20 trades are an observation window, not a claim of statistical
certainty. Reports rank setups and recorded signal features by net outcomes;
automatic disabling only applies to a setup after the 20-trade minimum.
"""
from core import performance


def confidence_band(confidence):
    value = float(confidence or 0)
    if value < 50: return "c40"
    if value < 65: return "c50"
    if value < 80: return "c65"
    return "c80"


def setup_key(direction, confidence, reward_risk, domain="futures", strategy="momentum"):
    rr = "rr2+" if float(reward_risk or 0) >= 2 else "rr1+"
    prefix = "" if domain == "futures" else f"{domain}:"
    safe_strategy = str(strategy or "momentum").strip().lower().replace(" ", "_")
    return f"{prefix}{safe_strategy}|{str(direction).upper()}|{confidence_band(confidence)}|{rr}"


class LearningEngine:
    def __init__(self, journal, min_samples=20, disable_below_r=0.1):
        self.journal = journal
        self.min_samples = int(min_samples)
        self.disable_below_r = float(disable_below_r)

    def allows(self, key):
        return key not in self.journal.disabled_setups()

    def evaluate(self):
        trades = self.journal.closed_trades()
        disabled_now = []
        already = self.journal.disabled_setups()
        by_setup = performance.compute(trades)["by_setup"]
        for key, stats in by_setup.items():
            if key in already or stats["trades"] < self.min_samples:
                continue
            exp_r = stats.get("expectancy_r")
            if exp_r is not None and exp_r < -self.disable_below_r:
                reason = (f"{stats['trades']} trades, expectancy {exp_r}R, "
                          f"win rate {stats['win_rate']}%")
                self.journal.set_setup_disabled(key, True, reason)
                disabled_now.append({"setup": key, "reason": reason})
        return disabled_now

    @staticmethod
    def _feature_groups(trades):
        groups = {}
        for trade in trades:
            context = trade.get("context") or {}
            features = context.get("features") or {}
            for feature, active in features.items():
                if active is True or (isinstance(active, (int, float)) and active > 0):
                    groups.setdefault(feature, []).append(trade)
        rows = []
        for name, items in groups.items():
            summary = performance.summarize(items)
            rows.append({"feature": name, **summary,
                         "mature": len(items) >= 20})
        return sorted(rows, key=lambda x: (x["expectancy"] or 0), reverse=True)

    def report(self):
        trades = self.journal.closed_trades()
        stats = performance.compute(trades)
        disabled = self.journal.disabled_setups()
        setups = []
        for key, item in stats["by_setup"].items():
            setups.append({"setup": key, **item,
                           "mature": item["trades"] >= self.min_samples,
                           "disabled": key in disabled,
                           "disabled_reason": disabled.get(key)})
        setups.sort(key=lambda s: s["trades"], reverse=True)
        suggestions = []
        if len(trades) < self.min_samples:
            suggestions.append(
                f"Only {len(trades)} closed trades: collect {self.min_samples} before changing strategy.")
        return {
            "min_samples": self.min_samples, "closed_trades": len(trades),
            "setups": setups, "features": self._feature_groups(trades),
            "disabled": disabled, "suggestions": suggestions,
            "learning_policy": "Observe first 20 closed trades; rank features by net expectancy; no automatic indicator deletion.",
        }
