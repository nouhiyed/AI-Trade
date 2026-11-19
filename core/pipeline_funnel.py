"""Thread-safe per-domain scan funnel for the latest 5m scan cycle."""
from collections import Counter
from threading import RLock
from time import time
from uuid import uuid4


STAGES = (
    "events_received",
    "passed_filter",
    "strategy_accepted",
    "valid_plan",
    "risk_approved",
    "trade_opened",
)


class PipelineFunnel:
    def __init__(self):
        self._lock = RLock()
        self._cycles = {}
        self._history = {}

    def start(self, domain, expected=0, timeframe="5m"):
        domain = str(domain).lower()
        with self._lock:
            now = time()
            candle_open = int(now // 300) * 300 if timeframe == "5m" else int(now)
            current = self._cycles.get(domain)
            if current and current.get("candle_open") == candle_open:
                current["expected"] = max(current["expected"], max(0, int(expected or 0)))
                current["success"] = False
                current.pop("finished_at", None)
                return current["cycle_id"]
            if current:
                history = self._history.setdefault(domain, [])
                history.append(self._serialize(current))
                self._history[domain] = history[-100:]
            cycle = {
                "cycle_id": uuid4().hex,
                "domain": domain,
                "timeframe": timeframe,
                "candle_open": candle_open,
                "started_at": now,
                "expected": max(0, int(expected or 0)),
                "processed": 0,
                "stages": {name: 0 for name in STAGES},
                "errors": 0,
                "fatal_errors": 0,
                "rejections": Counter(),
                "completion_pct": 0.0,
                "success": False,
            }
            self._cycles[domain] = cycle
            return cycle["cycle_id"]

    def record(self, domain, stage, count=1, reason=None, error=False,
               fatal=False, cycle_id=None):
        domain = str(domain).lower()
        with self._lock:
            cycle = self._cycles.get(domain)
            if cycle is None or (cycle_id and cycle["cycle_id"] != cycle_id):
                return False
            if stage in cycle["stages"]:
                cycle["stages"][stage] += max(0, int(count))
            if reason:
                cycle["rejections"][str(reason)] += max(1, int(count))
            if error:
                cycle["errors"] += max(1, int(count))
            if fatal:
                cycle["fatal_errors"] += max(1, int(count))
            return True

    def finish(self, domain, processed=None, expected=None, fatal=False):
        domain = str(domain).lower()
        with self._lock:
            cycle = self._cycles.get(domain)
            if cycle is None:
                return self.snapshot(domain)
            total = max(0, int(expected if expected is not None else cycle["expected"]))
            done = max(0, int(processed if processed is not None else
                               cycle["stages"]["events_received"]))
            cycle["expected"] = max(cycle["expected"], total)
            cycle["processed"] = cycle.get("processed", 0) + done
            cycle["completion_pct"] = round(
                (min(cycle["processed"], cycle["expected"]) /
                 cycle["expected"] * 100.0) if cycle["expected"] else 100.0, 2)
            if fatal:
                cycle["fatal_errors"] = max(1, cycle["fatal_errors"])
            cycle["success"] = (
                cycle["completion_pct"] >= 95.0
                and cycle["fatal_errors"] == 0
            )
            cycle["finished_at"] = time()
            cycle["top_rejections"] = [
                {"reason": reason, "count": count}
                for reason, count in cycle["rejections"].most_common(5)
            ]
            return self._serialize(cycle, self._history.get(domain, []))

    @staticmethod
    def _serialize(cycle, history=None):
        result = dict(cycle)
        result["rejections"] = dict(cycle["rejections"])
        result["top_rejections"] = [
            {"reason": reason, "count": count}
            for reason, count in cycle["rejections"].most_common(5)
        ]
        result["history"] = list(history or [])
        return result

    def snapshot(self, domain=None):
        with self._lock:
            if domain:
                key = str(domain).lower()
                cycle = self._cycles.get(key)
                return self._serialize(cycle, self._history.get(key, [])) if cycle else {
                    "domain": key, "available": False, "history": list(self._history.get(key, []))}
            return {key: self._serialize(value, self._history.get(key, []))
                    for key, value in self._cycles.items()}
