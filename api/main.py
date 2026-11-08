import json
import os
import math
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from core.coordinator import TradingCoordinator
from core.autopilot import Autopilot
from core.market_context import MarketContext
from core import performance

initial_balance = float(os.environ.get("DEMO_INITIAL_BALANCE", "1000"))
if not math.isfinite(initial_balance) or initial_balance <= 0:
    raise ValueError("DEMO_INITIAL_BALANCE must be a finite positive number")
coordinator = TradingCoordinator(initial_balance=initial_balance)
autopilot = Autopilot(coordinator, context=MarketContext())

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
                    symbols = coordinator.market_feed.fetch_alpha_symbols()
                elif market in {"spot", "futures"}:
                    symbols = coordinator.market_feed.fetch_symbols(market)
                else:
                    return self.send_json({"error": "Unsupported market"}, 400)
                return self.send_json({
                    "market": market,
                    "symbols": symbols,
                    "source": "binance_rest"
                })

            if path == "/market/candles":
                market = params.get("market", ["spot"])[0].lower()
                symbol = params.get("symbol", ["BTCUSDT"])[0].upper()
                interval = params.get("interval", ["5m"])[0]
                limit = int(params.get("limit", ["200"])[0])
                if interval not in {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"}:
                    return self.send_json({"error": "Unsupported interval"}, 400)
                live = params.get("live", ["0"])[0] == "1"
                if market == "alpha":
                    candles = coordinator.market_feed.fetch_alpha_candles(
                        symbol, interval, limit=min(max(limit, 2), 1000)
                    )
                elif market in {"spot", "futures"}:
                    candles = coordinator.market_feed.fetch_candles(
                        market, symbol, interval,
                        limit=min(max(limit, 2), 1000),
                        closed_only=not live,
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
            if path == "/performance":
                return self.send_json(
                    performance.compute(coordinator.journal.closed_trades()))
            if path == "/journal":
                limit = min(max(int(params.get("limit", ["50"])[0]), 1), 500)
                return self.send_json({"trades": coordinator.journal.recent(limit)})
            if path == "/learning":
                return self.send_json(coordinator.learning.report())
            if path == "/autopilot":
                return self.send_json(autopilot.status())
            if path == "/health":
                return self.send_json({"ok": True, "mode": coordinator.mode})
            if path == "/status":
                return self.send_json({
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
                result = coordinator.submit_chart_signal(
                    domain=data.get("domain", ""),
                    symbol=data.get("symbol", ""),
                    timeframe=data.get("timeframe", "5m"),
                )
                return self.send_json(
                    result, 200 if result.get("success") else 400
                )

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
