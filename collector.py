
import requests
import pandas as pd
import json
import os
from datetime import datetime, timezone

BASE = "https://api.binance.com"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
INTERVALS = ["1m", "5m", "15m", "1h", "4h", "1d"]

os.makedirs("data/raw", exist_ok=True)

def get_data(endpoint, params):
    response = requests.get(
        BASE + endpoint,
        params=params,
        timeout=20
    )
    response.raise_for_status()
    return response.json()

def collect(symbol):
    print(f"\nCollecting {symbol}...")

    for interval in INTERVALS:
        candles = get_data(
            "/api/v3/klines",
            {"symbol": symbol, "interval": interval, "limit": 500}
        )

        columns = [
            "open_time", "open", "high", "low", "close",
            "volume", "close_time", "quote_volume",
            "trades", "taker_buy_base", "taker_buy_quote", "ignore"
        ]

        df = pd.DataFrame(candles, columns=columns)

        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col])

        df["open_time"] = pd.to_datetime(
            df["open_time"], unit="ms", utc=True
        )

        path = f"data/raw/{symbol}_{interval}.csv"
        df.to_csv(path, index=False)
        print(f"Saved {path}: {len(df)} candles")

    book = get_data(
        "/api/v3/depth",
        {"symbol": symbol, "limit": 100}
    )

    bids = [[float(p), float(q)] for p, q in book["bids"]]
    asks = [[float(p), float(q)] for p, q in book["asks"]]

    best_bid = bids[0][0]
    best_ask = asks[0][0]
    spread = best_ask - best_bid
    midpoint = (best_ask + best_bid) / 2

    bid_volume = sum(q for p, q in bids)
    ask_volume = sum(q for p, q in asks)

    snapshot = {
        "symbol": symbol,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "lastUpdateId": book["lastUpdateId"],
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": spread,
        "spread_percent": spread / midpoint * 100,
        "bid_volume": bid_volume,
        "ask_volume": ask_volume,
        "imbalance": (
            (bid_volume - ask_volume) /
            (bid_volume + ask_volume)
            if bid_volume + ask_volume else 0
        ),
        "bids": bids,
        "asks": asks
    }

    filename = f"data/raw/{symbol}_orderbook.json"

    with open(filename, "w") as f:
        json.dump(snapshot, f, indent=2)

    print(f"Order book saved: {filename}")
    print(f"Spread: {spread:.6f}")
    print(f"Imbalance: {snapshot['imbalance']:.4f}")

for symbol in SYMBOLS:
    try:
        collect(symbol)
    except Exception as error:
        print(f"ERROR {symbol}: {error}")

print("\nCollection finished.")
