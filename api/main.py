import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from core.coordinator import TradingCoordinator

coordinator = TradingCoordinator(initial_balance=1000)

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
        path = urlparse(self.path).path
        try:
            if path == "/health":
                return self.send_json({"ok": True, "mode": coordinator.mode})
            if path == "/status":
                return self.send_json({
                    "system": coordinator.get_system_status(),
                    "controls": coordinator.get_agent_controls(),
                    "paper": coordinator.get_paper_status()
                })
            if path == "/paper/history":
                return self.send_json(coordinator.paper.get_trade_history())
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

            if path == "/analyze":
                symbol = data.get("symbol", "BTCUSDT")
                return self.send_json(coordinator.analyze_live(symbol))

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

            if path == "/paper/open":
                result = coordinator.request_paper_trade(
                    domain=data["domain"],
                    symbol=data["symbol"],
                    direction=data["direction"],
                    entry=data["entry"],
                    quantity=data["quantity"],
                    leverage=data.get("leverage", 1),
                    stop_loss=data.get("stop_loss"),
                    take_profit=data.get("take_profit")
                )
                return self.send_json(result)

            if path == "/paper/close":
                result = coordinator.close_paper_position_at_market(
                    position_id=data["position_id"],
                    quantity=data.get("quantity")
                )
                return self.send_json(result)

            if path == "/mode":
                result = coordinator.set_mode(data.get("mode", "PAPER"))
                return self.send_json(result, 200 if result.get("success") else 400)

            if path == "/demo/close":
                result = coordinator.close_demo_position(data["position_id"])
                return self.send_json(result, 200 if result.get("success") else 400)

            if path == "/demo/open":
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

def paper_monitor_worker():
    print("[PAPER] Automatic position monitor started")
    while True:
        try:
            result = coordinator.monitor_paper_positions()
            for event in result.get("events", []):
                if event.get("reason"):
                    print("[PAPER] Auto-close:", event)
                elif event.get("error"):
                    print("[PAPER] Monitor error:", event)
        except Exception as error:
            print("[PAPER] Monitor cycle error:", error)
        time.sleep(2)


if __name__ == "__main__":
    monitor_thread = threading.Thread(
        target=paper_monitor_worker,
        name="paper-position-monitor",
        daemon=True,
    )
    monitor_thread.start()

    print("AI-Trader API: http://127.0.0.1:8000")
    ThreadingHTTPServer(("127.0.0.1", 8000), APIHandler).serve_forever()
