"""Learning engine: learns from closed trades without changing strategy randomly.

Rules (deliberately conservative):
  * trades are grouped by a *setup key* (direction + confidence band + reward/risk band);
  * nothing changes until a setup has ``min_samples`` closed trades;
  * a setup whose average result is below ``-disable_below_r`` (in R multiples) is
    switched off automatically and the reason is stored; it can be re-enabled by hand;
  * parameter changes (e.g. a higher minimum confidence) are only *suggested*.
"""
from core import performance


def confidence_band(confidence):
    value = float(confidence or 0)
    if value < 50:
        return "c40"
    if value < 65:
        return "c50"
    if value < 80:
        return "c65"
    return "c80"


def setup_key(direction, confidence, reward_risk, domain="futures"):
    rr = "rr2+" if float(reward_risk or 0) >= 2 else "rr1.5"
    prefix = "" if domain == "futures" else f"{domain}:"
    return f"{prefix}{str(direction).upper()}|{confidence_band(confidence)}|{rr}"


class LearningEngine:

    def __init__(self, journal, min_samples=30, disable_below_r=0.1):
        self.journal = journal
        self.min_samples = int(min_samples)
        self.disable_below_r = float(disable_below_r)

    def allows(self, key):
        return key not in self.journal.disabled_setups()

    def evaluate(self):
        """Re-check every setup; returns the list of setups disabled in this run."""
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

    def report(self):
        trades = self.journal.closed_trades()
        stats = performance.compute(trades)
        disabled = self.journal.disabled_setups()
        setups = []
        for key, item in stats["by_setup"].items():
            setups.append({
                "setup": key, **item,
                "mature": item["trades"] >= self.min_samples,
                "disabled": key in disabled,
                "disabled_reason": disabled.get(key),
            })
        setups.sort(key=lambda s: s["trades"], reverse=True)

        suggestions = []
        bands = {}
        for trade in trades:
            band = str(trade["setup_key"]).split("|")[1]
            bands.setdefault(band, []).append(trade)
        mature = {b: performance.summarize(v) for b, v in bands.items()
                  if len(v) >= self.min_samples}
        positive = [b for b, s in mature.items() if (s["expectancy_r"] or 0) > 0]
        negative = [b for b, s in mature.items() if (s["expectancy_r"] or 0) <= 0]
        if positive and negative:
            suggestions.append(
                "Confidence bands %s are profitable while %s are not: consider "
                "raising the minimum confidence." % (sorted(positive), sorted(negative)))
        if len(trades) < self.min_samples:
            suggestions.append(
                "Only %d closed trades so far: no conclusions before %d."
                % (len(trades), self.min_samples))
        return {
            "min_samples": self.min_samples,
            "closed_trades": len(trades),
            "setups": setups,
            "disabled": disabled,
            "suggestions": suggestions,
        }
