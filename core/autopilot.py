"""Autopilot: scans the market on a timer and opens DEMO trades by itself.

Safety: off by default; every trade still goes through the signal match, trade
plan checks, risk reservation and the learning engine's setup filter.
"""
import json
import threading
import time
from pathlib import Path

from core.learning import setup_key

DEFAULTS = {
    "enabled": False,
    "interval_sec": 120,
    "scan_limit": 12,
    "min_confidence": 60.0,
    "max_concurrent": 3,
    "risk_pct": 0.5,
    "cooldown_min": 30,
    "use_context": True,
    "trade_futures": True,
    "trade_spot": True,

}
LIMITS = {
    "interval_sec": (30, 3600), "scan_limit": (3, 40),
    "min_confidence": (25.0, 100.0), "max_concurrent": (1, 5),
    "risk_pct": (0.05, 1.0), "cooldown_min": (0, 1440),
}


class Autopilot:

    def __init__(self, coordinator, context=None, config_path="config/autopilot.json",
                 clock=time.time):
        self.c = coordinator
        self.context = context
        self.path = Path(config_path)
        self.clock = clock
        self.config = dict(DEFAULTS)
        self.last_run = None
        self.last_result = {}
        self._cooldown = {}          # symbol -> unix time when it may trade again
        self._lock = threading.Lock()
        self._load()

    # ---- config ------------------------------------------------------------

    def _load(self):
        try:
            saved = json.loads(self.path.read_text())
            if isinstance(saved, dict):
                self.update(saved, persist=False)
        except Exception:
            pass

    def update(self, changes, persist=True):
        for key, value in (changes or {}).items():
            if key not in DEFAULTS:
                continue
            default = DEFAULTS[key]
            if isinstance(default, bool):
                if isinstance(value, bool):
                    self.config[key] = value
                elif isinstance(value, int) and value in (0, 1):
                    self.config[key] = bool(value)
                # Do not treat strings such as "false" as truthy.
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if number != number:
                continue
            lo, hi = LIMITS[key]
            number = min(max(number, lo), hi)
            self.config[key] = int(number) if isinstance(default, int) else number
        if persist:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.config, indent=2))
        return self.status()

    def status(self):
        return {"config": dict(self.config), "last_run": self.last_run,
                "last_result": self.last_result,
                "cooldowns": {k: int(v - self.clock())
                              for k, v in self._cooldown.items() if v > self.clock()}}

    # ---- one scan cycle --------------------------------------------------------

    def _open_symbols(self):
        return {str(p.get("symbol")).upper()
                for p in self.c.demo_positions.values()
                if p.get("status") in ("DEMO_OPEN", "DEMO_PARTIALLY_CLOSED",
                                       "DEMO_UNPROTECTED",
                                       "DEMO_RECONCILIATION_REQUIRED")}

    def tick(self, force=False):
        """Run one cycle and always publish its latest outcome."""
        with self._lock:
            cfg = dict(self.config)
            result = {"status": "RUNNING", "opened": [], "skipped": [],
                      "scanned": 0, "actionable": 0}
            self.last_run = int(self.clock())
            self.last_result = dict(result)

            if not (cfg["enabled"] or force):
                result["status"] = "IDLE"
                result["skipped"].append({"reason": "Autopilot is off"})
                self.last_result = result
                return result
            if self.c.mode != "DEMO":
                result["status"] = "SKIPPED"
                result["skipped"].append({"reason": "Not in DEMO mode"})
                self.last_result = result
                return result

            try:
                open_symbols = self._open_symbols()
                slots = int(cfg["max_concurrent"]) - len(open_symbols)
                if slots <= 0:
                    result["skipped"].append(
                        {"reason": "Max concurrent trades reached"})

                sources = []
                limit = int(cfg["scan_limit"])
                if cfg["trade_futures"]:
                    sources.append(("futures", lambda: self.c.scan_futures(limit=limit)))
                if cfg["trade_spot"]:
                    sources.append(("spot", lambda: self.c.scan_spot(limit=min(limit, 8))))

                # Scan every enabled market independently. One failed scanner or
                # domain processor must not hide results from the other domains.
                for domain, scan_fn in sources:
                    try:
                        scan = scan_fn()
                        if not isinstance(scan, dict):
                            raise TypeError("Scanner returned an invalid response")
                        result["scanned"] += scan.get("scanned") or 0
                        result["actionable"] += scan.get("actionable") or 0
                        if scan.get("rejections"):
                            result.setdefault("rejections", {})[domain] = scan["rejections"]
                        if scan.get("rejection_samples"):
                            result.setdefault("rejection_samples", []).extend(
                                scan["rejection_samples"][:8])
                        if not scan.get("success"):
                            result["skipped"].append({
                                "domain": domain,
                                "reason": scan.get("reason", "Scan failed"),
                            })
                            continue
                        slots = self._process(
                            domain, scan, cfg, open_symbols, slots, result)
                    except Exception as error:
                        result["skipped"].append({
                            "domain": domain,
                            "reason": "Domain processing error: " + str(error),
                        })
                result["status"] = "COMPLETED"
            except Exception as error:
                result["status"] = "ERROR"
                result["error"] = str(error)
                result["skipped"].append({
                    "reason": "Autopilot cycle error: " + str(error),
                })
            finally:
                # Never leave the dashboard showing a previous cycle's result.
                self.last_result = result
            return result

    def _process(self, domain, scan, cfg, open_symbols, slots, result):
        for opp in scan.get("opportunities", []):
            if slots <= 0:
                break
            symbol = str(opp.get("symbol", "")).upper()
            try:
                direction = opp["direction"]
                signal, plan = opp["signal"], opp["trade_plan"]
                confidence = float(opp.get("confidence") or 0)

                def skip(reason):
                    result["skipped"].append({
                        "domain": domain, "symbol": symbol, "reason": str(reason)})

                if not symbol:
                    skip("Missing symbol")
                    continue
                if symbol in open_symbols:
                    skip("Already open")
                    continue
                if self._cooldown.get(symbol, 0) > self.clock():
                    skip("Cooldown after a recent trade")
                    continue
                if confidence < float(cfg["min_confidence"]):
                    skip("Confidence below minimum")
                    continue

                key = setup_key(
                    direction, confidence, plan.get("reward_risk"), domain)
                if not self.c.learning.allows(key):
                    skip("Setup disabled by learning: " + key)
                    continue

                assessment = None
                if cfg["use_context"] and self.context is not None:
                    assessment = self.context.assess(symbol, direction)
                    if assessment.get("veto"):
                        skip("Context veto: " + assessment["veto"])
                        continue
                    confidence += assessment["score"] * 5
                    if confidence < float(cfg["min_confidence"]):
                        skip("Confidence below minimum after context")
                        continue

                signal = dict(signal)
                signal["market_context"] = assessment
                signal["setup_key"] = key
                signal["confidence_adjusted"] = confidence
                self.c.last_signals[domain] = signal

                selected_leverage = 1
                if domain == "futures":
                    selected_leverage = self.c.select_futures_leverage(signal, plan)
                    trade = self.c.request_demo_futures_trade(
                        symbol, direction, risk_pct=float(cfg["risk_pct"]),
                        leverage=selected_leverage)
                else:
                    trade = self.c.request_demo_spot_trade(
                        symbol, domain=domain, risk_pct=float(cfg["risk_pct"]))

                if trade.get("approved"):
                    slots -= 1
                    open_symbols.add(symbol)
                    self._cooldown[symbol] = (
                        self.clock() + cfg["cooldown_min"] * 60)
                    result["opened"].append({
                        "domain": domain, "symbol": symbol,
                        "direction": direction,
                        "leverage": trade.get("leverage", selected_leverage),
                        "trade_id": trade.get("trade_id"),
                    })
                else:
                    skip(trade.get("reason", "Rejected"))
            except Exception as error:
                # Isolate malformed opportunities and transient agent errors.
                result["skipped"].append({
                    "domain": domain, "symbol": symbol,
                    "reason": "Opportunity processing error: " + str(error),
                })
        return slots

    def run_forever(self, stop_event=None):
        print("[AUTOPILOT] worker started")
        while not (stop_event and stop_event.is_set()):
            try:
                if self.config["enabled"]:
                    summary = self.tick()
                    if summary.get("opened"):
                        print("[AUTOPILOT] opened:", summary["opened"])
                    pause = max(5, float(self.config["interval_sec"]))
                else:
                    pause = 5
            except Exception as error:
                print("[AUTOPILOT] cycle error:", error)
                pause = 30
            time.sleep(pause)
