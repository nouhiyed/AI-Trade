import json
import os
import math
import threading
import time
import sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from uuid import uuid4

API_VERSION = "2026.11.10.4"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.coordinator import TradingCoordinator
from core.autopilot import Autopilot
from core.market_context import MarketContext
from core import performance

initial_balance = float(os.environ.get("DEMO_INITIAL_BALANCE", "1000"))
if not math.isfinite(initial_balance) or initial_balance <= 0:
    raise ValueError("DEMO_INITIAL_BALANCE must be a finite positive number")
coordinator = TradingCoordinator(initial_balance=initial_balance)
autopilot = Autopilot(coordinator, context=MarketContext())
submission_store_path = PROJECT_ROOT / "data" / "agent_submissions.json"
submission_jobs = {}
submission_jobs_lock = threading.Lock()


def _save_submission_jobs_locked():
    submission_store_path.parent.mkdir(parents=True, exist_ok=True)
    temp = submission_store_path.with_suffix(".tmp")
    temp.write_text(json.dumps(submission_jobs, indent=2, default=str))
    temp.replace(submission_store_path)


def _load_submission_jobs():
    try:
        raw = json.loads(submission_store_path.read_text())
        if not isinstance(raw, dict):
            return {}
        now = time.time()
        jobs = {}
        for key, value in raw.items():
            if not isinstance(value, dict) or now - float(value.get("created_at", now)) > 7 * 86400:
                continue
            job = dict(value)
            if job.get("status") == "PROCESSING":
                job["status"] = "FAILED"
                job["reason"] = "Server restarted before the agent decision was saved"
            jobs[str(key)] = job
        return jobs
    except (FileNotFoundError, ValueError, TypeError):
        return {}


submission_jobs = _load_submission_jobs()


def _process_agent_submission(request_id, payload):
    failed = False
    try:
        result = coordinator.submit_chart_signal(
            domain=payload.get("domain", ""),
            symbol=payload.get("symbol", ""),
            timeframe=payload.get("timeframe", "5m"),
            entry_price=payload.get("entry_price"),
            take_profit=payload.get("take_profit"),
            stop_loss=payload.get("stop_loss"),
        )
    except Exception as error:
        failed = True
        result = {
            "success": False,
            "opened": False,
            "decision_status": "REJECTED",
            "decision_reason": str(error),
            "reason": str(error),
        }
    if not isinstance(result, dict):
        failed = True
        result = {
            "success": False,
            "opened": False,
            "decision_status": "REJECTED",
            "decision_reason": "Agent returned an invalid response",
            "reason": "Agent returned an invalid response",
        }
    # A completed analysis, including a rejection, is a completed decision.
    result.setdefault("decision_status", "REJECTED")
    result.setdefault(
        "decision_reason",
        result.get("reason") or "Agent did not provide a decision reason",
    )
    with submission_jobs_lock:
        job = submission_jobs.get(request_id)
        if job is not None:
            job["status"] = "FAILED" if failed else "COMPLETED"
            job["result"] = result
            job["decision_status"] = result.get("decision_status")
            job["reason"] = result.get("decision_reason") or result.get("reason")
            job["completed_at"] = time.time()
            try:
                _save_submission_jobs_locked()
            except Exception as error:
                # Keep the in-memory result readable even if local persistence fails.
                job["persistence_error"] = str(error)


class APIHandler(BaseHTTPRequestHandler):
    def send_json(self, data, code=200):
        body = json.dumps(data, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        try:
            if path == "/market/symbols":
                market = params.get("market", ["spot"])[0].lower()
                if market == "alpha":
                    symbols = coordinator.alpha_feed.symbols()
                    source = "binance_alpha"
                elif market in {"spot", "futures"}:
                    symbols = coordinator.market_feed.fetch_symbols(market)
                    source = "binance_rest"
                else:
                    return self.send_json({"error": "Unsupported market"}, 400)
                return self.send_json({
                    "market": market,
                    "symbols": symbols,
                    "count": len(symbols),
                    "source": source,
                    "received_at": time.time(),
                })

            if path == "/market/candles":
                market = params.get("market", ["spot"])[0].lower()
                symbol = params.get("symbol", ["BTCUSDT"])[0].upper()
                interval = params.get("interval", ["5m"])[0]
                limit = int(params.get("limit", ["200"])[0])
                if interval not in {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"}:
                    return self.send_json({"error": "Unsupported interval"}, 400)
                live = params.get("live", ["0"])[0] == "1"
                start_time = params.get("startTime", [None])[0]
                end_time = params.get("endTime", [None])[0]
                start_time = int(start_time) if start_time is not None else None
                end_time = int(end_time) if end_time is not None else None
                if market == "alpha":
                    candles = coordinator.market_feed.fetch_alpha_candles(
                        symbol, interval, limit=min(max(limit, 2), 1000),
                        start_time=start_time, end_time=end_time,
                    )
                elif market in {"spot", "futures"}:
                    candles = coordinator.market_feed.fetch_candles(
                        market, symbol, interval,
                        limit=min(max(limit, 2), 1000),
                        closed_only=not live,
                        start_time=start_time, end_time=end_time,
                    )
                else:
                    return self.send_json({"error": "Unsupported market"}, 400)
                records = []
                for row in candles.itertuples(index=False):
                    records.append({
                        "time": int(row.open_time.timestamp()),
                        "open": float(row.open),
                        "high": float(row.high),
                        "low": float(row.low),
                        "close": float(row.close),
                        "volume": float(row.volume)
                    })
                return self.send_json({
                    "market": market,
                    "symbol": symbol,
                    "interval": interval,
                    "candles": records,
                    "source": candles.attrs.get("source", "binance_rest"),
                    "received_at": candles.attrs.get("received_at")
                })
            if path == "/journal/chart":
                trade_id = str(params.get("trade_id", [""])[0]).strip()
                if not trade_id:
                    return self.send_json({"success": False, "reason": "Missing trade_id"}, 400)
                trade = next(
                    (item for item in coordinator.journal.closed_trades()
                     if str(item.get("trade_id")) == trade_id),
                    None,
                )
                if trade is None:
                    trade = next(
                        (dict(item) for key, item in coordinator.demo_positions.items()
                         if str(key) == trade_id
                         and str(item.get("status", "")).upper() in {"DEMO_CLOSED", "CLOSED"}),
                        None,
                    )
                if trade is None:
                    return self.send_json({"success": False, "reason": "Trade not found in archive"}, 404)

                context = trade.get("context") or {}
                if not isinstance(context, dict):
                    context = {}
                saved_timeframe = (
                    trade.get("timeframe")
                    or context.get("chart_timeframe")
                    or context.get("timeframe")
                )
                timeframe_recorded = bool(saved_timeframe)
                timeframe = str(saved_timeframe or "5m").lower()
                interval_ms = {
                    "1m": 60000, "3m": 180000, "5m": 300000,
                    "15m": 900000, "30m": 1800000, "1h": 3600000,
                    "2h": 7200000, "4h": 14400000, "6h": 21600000,
                    "8h": 28800000, "12h": 43200000, "1d": 86400000,
                }
                if timeframe not in interval_ms:
                    timeframe = "5m"
                step = interval_ms[timeframe]

                def stamp(value):
                    number = int(value or 0)
                    return number * 1000 if 0 < number < 1000000000000 else number

                opened = stamp(trade.get("opened_at") or trade.get("opened_at_ms"))
                closed = stamp(trade.get("closed_at") or trade.get("closed_at_ms"))
                if opened:
                    start_time = max(0, opened - 35 * step)
                    end_time = (closed or opened + 120 * step) + 35 * step
                    if end_time - start_time > 999 * step:
                        start_time = max(0, end_time - 999 * step)
                else:
                    start_time = end_time = None

                domain = str(trade.get("domain", "futures")).lower()
                market = "spot" if domain == "spot" else "futures"
                symbol = str(trade.get("symbol", "")).upper()
                if not symbol:
                    return self.send_json({"success": False, "reason": "Trade symbol is missing"}, 400)

                if domain == "alpha":
                    candles_frame = coordinator.market_feed.fetch_alpha_candles(
                        symbol, timeframe, limit=1000,
                        start_time=start_time, end_time=end_time,
                    )
                else:
                    candles_frame = coordinator.market_feed.fetch_candles(
                        market, symbol, timeframe, limit=1000,
                        closed_only=False, start_time=start_time, end_time=end_time,
                    )
                candles = candles_frame[["open", "high", "low", "close"]].to_dict("records")
                entry = trade.get("entry") or trade.get("entry_price")
                stop = trade.get("stop_loss")
                target = trade.get("take_profit")
                exit_price = trade.get("exit_price") or trade.get("close_price")
                if entry is None or stop is None or target is None:
                    return self.send_json({
                        "success": False,
                        "reason": "This archived trade is missing entry or protection levels",
                    }, 422)
                candle_records = []
                for row in candles_frame.itertuples(index=False):
                    candle_records.append({
                        "time": int(row.open_time.timestamp()),
                        "open": float(row.open),
                        "high": float(row.high),
                        "low": float(row.low),
                        "close": float(row.close),
                        "volume": float(row.volume),
                    })
                return self.send_json({
                    "success": True,
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "market": domain,
                    "timeframe": timeframe,
                    "timeframe_recorded": timeframe_recorded,
                    "candles": candle_records,
                    "entry": entry,
                    "exit": exit_price,
                    "stop_loss": stop,
                    "take_profit": target,
                    "net_pnl": trade.get("net_pnl"),
                    "close_reason": trade.get("close_reason"),
                    "opened_at": opened,
                    "closed_at": closed,
                })

            if path == "/performance":
                return self.send_json(
                    performance.compute(coordinator.journal.closed_trades()))
            if path == "/journal":
                if params.get("closed", ["0"])[0] == "1":
                    trades = coordinator.journal.closed_trades()
                    trades.sort(
                        key=lambda item: int(item.get("closed_at") or 0),
                        reverse=True,
                    )
                    return self.send_json({
                        "trades": trades,
                        "count": len(trades),
                        "archive": True,
                    })
                limit = min(max(int(params.get("limit", ["50"])[0]), 1), 500)
                return self.send_json({"trades": coordinator.journal.recent(limit)})
            if path == "/learning":
                return self.send_json(coordinator.learning.report())
            if path == "/autopilot":
                return self.send_json(autopilot.status())
            if path == "/agent/submission":
                request_id = str(params.get("id", [""])[0]).strip()
                with submission_jobs_lock:
                    job = submission_jobs.get(request_id)
                    snapshot = dict(job) if job else None
                if snapshot is None:
                    return self.send_json({
                        "success": False,
                        "request_status": "NOT_FOUND",
                        "reason": "Agent submission request was not found",
                    }, 404)
                response = {
                    "success": True,
                    "request_id": request_id,
                    "request_status": snapshot["status"],
                    "created_at": snapshot.get("created_at"),
                    "completed_at": snapshot.get("completed_at"),
                    "decision_status": snapshot.get("decision_status"),
                    "decision_reason": snapshot.get("reason"),
                    "message": (
                        "Agent decision is ready" if snapshot["status"] == "COMPLETED"
                        else snapshot.get("reason") or "Request is being processed"
                    ),
                }
                if snapshot["status"] in {"COMPLETED", "FAILED"}:
                    response["result"] = snapshot.get("result")
                if snapshot["status"] == "FAILED":
                    response["reason"] = snapshot.get("reason", "Agent request failed")
                return self.send_json(response)
            if path == "/notifications/status":
                return self.send_json(coordinator.notifier.status())

            if path == "/health":
                return self.send_json({"ok": True, "mode": coordinator.mode, "api_version": API_VERSION})
            if path == "/status":
                return self.send_json({
                    "api_version": API_VERSION,
                    "system": coordinator.get_system_status(),
                    "controls": coordinator.get_agent_controls(),
                    "demo": coordinator.get_demo_positions()
                })
            return self.send_json({"error": "Not found"}, 404)
        except Exception as e:
            return self.send_json({"error": str(e)}, 500)

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        try:
            data = self.read_body()

            if path == "/notifications/configure":
                status = coordinator.notifier.configure(data.get("bot_token"), data.get("chat_id"))
                return self.send_json({"success": True, **status})

            if path == "/notifications/test":
                sent = coordinator.notifier.send_message(
                    "AI-Trader Telegram connection test: notifications are working."
                )
                status = coordinator.notifier.status()
                return self.send_json({"success": sent, "sent": sent,
                    "reason": status.get("last_error"), "status": status},
                    200 if sent else 503)

            if path == "/scan/futures":
                return self.send_json(
                    coordinator.scan_futures(
                        limit=data.get("limit", 12),
                        min_quote_volume=data.get("min_quote_volume"),
                    )
                )

            if path == "/scan/spot":
                return self.send_json(coordinator.scan_spot(limit=data.get("limit", 8)))

            if path == "/scan/alpha":
                return self.send_json(coordinator.scan_alpha(limit=data.get("limit", 6)))

            if path == "/analyze":
                symbol = data.get("symbol", "BTCUSDT")
                return self.send_json(coordinator.analyze_live(symbol))

            if path == "/agent/submit":
                request_id = uuid4().hex
                now = time.time()
                with submission_jobs_lock:
                    expired = [
                        key for key, value in submission_jobs.items()
                        if now - value.get("created_at", now) > 7 * 86400
                    ]
                    for key in expired:
                        submission_jobs.pop(key, None)
                    while len(submission_jobs) >= 500:
                        oldest = min(
                            submission_jobs,
                            key=lambda key: submission_jobs[key].get("created_at", 0),
                        )
                        submission_jobs.pop(oldest, None)
                    submission_jobs[request_id] = {
                        "status": "PROCESSING",
                        "created_at": now,
                        "payload": dict(data),
                    }
                    _save_submission_jobs_locked()
                threading.Thread(
                    target=_process_agent_submission,
                    args=(request_id, dict(data)),
                    name="agent-submission-" + request_id[:8],
                    daemon=True,
                ).start()
                return self.send_json({
                    "success": True,
                    "request_id": request_id,
                    "request_status": "RECEIVED",
                    "decision_status": "PROCESSING",
                    "message": "Agent submission received and queued",
                }, 202)

            if path == "/emergency-stop":
                return self.send_json(coordinator.emergency_stop_all())

            if path == "/resume-all":
                return self.send_json(coordinator.resume_all_agents())

            if path.startswith("/agents/"):
                parts = path.split("/")
                if len(parts) == 4:
                    domain, action = parts[2], parts[3]
                    if action == "stop":
                        return self.send_json(coordinator.emergency_stop_agent(domain))
                    if action == "resume":
                        return self.send_json(coordinator.resume_agent(domain))

            if path == "/autopilot":
                return self.send_json(autopilot.update(data))

            if path == "/autopilot/run":
                return self.send_json(autopilot.tick(force=True))

            if path == "/learning/enable":
                key = str(data.get("setup", ""))
                coordinator.journal.set_setup_disabled(key, False, "manual re-enable")
                return self.send_json({"success": True, "setup": key})

            if path == "/mode":
                result = coordinator.set_mode(data.get("mode", "DEMO"))
                return self.send_json(result, 200 if result.get("success") else 400)

            if path == "/demo/deposit":
                if "amount" not in data:
                    return self.send_json({"success": False, "error": "Missing field: amount"}, 400)
                result = coordinator.deposit_demo_balance(data["amount"])
                return self.send_json(result, 200 if result.get("success") else 400)

            if path == "/demo/close":
                result = coordinator.close_demo_position(data["position_id"])
                return self.send_json(result, 200 if result.get("success") else 400)

            if path == "/demo/open":
                domain = str(data.get("domain", "futures")).lower()
                if domain in ("spot", "alpha"):
                    result = coordinator.request_demo_spot_trade(
                        symbol=data["symbol"], domain=domain,
                        risk_pct=data.get("risk_pct", 0.5))
                else:
                    result = coordinator.request_demo_futures_trade(
                        symbol=data["symbol"],
                        direction=data["direction"],
                        risk_pct=data.get("risk_pct", 0.5),
                        leverage=data.get("leverage", 1)
                    )
                return self.send_json(result, 200 if result.get("approved") else 400)

            return self.send_json({"error": "Not found"}, 404)

        except KeyError as e:
            return self.send_json({"error": "Missing field: " + str(e)}, 400)
        except Exception as e:
            return self.send_json({"success": False, "error": str(e)}, 400)

    def log_message(self, format, *args):
        print("[API]", format % args)

def demo_monitor_worker():
    print("[DEMO] Automatic position monitor started")
    while True:
        try:
            result = coordinator.monitor_demo_positions()
            for event in result.get("events", []):
                if event.get("reason"):
                    print("[DEMO] Auto-close:", event)
                elif event.get("error"):
                    print("[DEMO] Monitor error:", event)
        except Exception as error:
            print("[DEMO] Monitor cycle error:", error)
        time.sleep(2)


if __name__ == "__main__":
    monitor_thread = threading.Thread(
        target=demo_monitor_worker,
        name="demo-position-monitor",
        daemon=True,
    )
    monitor_thread.start()
    threading.Thread(target=autopilot.run_forever, name="autopilot",
                     daemon=True).start()

    host = os.environ.get("AI_TRADER_HOST", "127.0.0.1")
    port = int(os.environ.get("AI_TRADER_PORT", "8000"))
    print(f"AI-Trader API: http://{host}:{port}")
    ThreadingHTTPServer((host, port), APIHandler).serve_forever()
