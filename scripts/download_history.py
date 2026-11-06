
import csv
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
INTERVALS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
}

DAYS = 40
BASES = [
    "https://data-api.binance.vision",
    "https://api.binance.com",
]

FIELDS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_asset_volume", "number_of_trades",
    "taker_buy_base_volume", "taker_buy_quote_volume", "ignore"
]

OUT = Path("data/history")
OUT.mkdir(parents=True, exist_ok=True)


def fetch(symbol, interval, start, end):
    params = urllib.parse.urlencode({
        "symbol": symbol,
        "interval": interval,
        "startTime": start,
        "endTime": end,
        "limit": 1000
    })

    last_error = None

    for base in BASES:
        url = f"{base}/api/v3/klines?{params}"

        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "AI-Trader-Historical-Data"}
                )
                with urllib.request.urlopen(req, timeout=25) as response:
                    return json.loads(response.read().decode())
            except Exception as exc:
                last_error = exc
                time.sleep(2 * (attempt + 1))

    raise RuntimeError(str(last_error))


now = int(time.time() * 1000)
start_time = now - DAYS * 24 * 60 * 60 * 1000

for symbol in SYMBOLS:
    for interval, step in INTERVALS.items():
        print(f"\nDownloading {symbol} {interval}...", flush=True)

        rows = []
        cursor = start_time

        while cursor < now:
            batch = fetch(symbol, interval, cursor, now)

            if not batch:
                break

            for row in batch:
                if int(row[6]) < now:
                    rows.append(row)

            next_cursor = int(batch[-1][0]) + step

            if next_cursor <= cursor:
                break

            cursor = next_cursor
            print(f"  Candles: {len(rows)}", flush=True)
            time.sleep(0.15)

        rows.sort(key=lambda x: int(x[0]))

        path = OUT / f"{symbol}_{interval}.csv"
        temp = path.with_suffix(".tmp")

        with open(temp, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(FIELDS)
            writer.writerows(rows)

        temp.replace(path)

        print(
            f"SAVED {path} | {len(rows)} candles",
            flush=True
        )

print("\nHISTORICAL DOWNLOAD COMPLETE", flush=True)

