import json
import os
import glob
import numpy as np


def analyze_orderbook(book):
    bids = np.array(book["bids"], dtype=float)
    asks = np.array(book["asks"], dtype=float)

    best_bid = bids[0, 0]
    best_ask = asks[0, 0]
    mid = (best_ask + best_bid) / 2

    bid_volume = bids[:, 1].sum()
    ask_volume = asks[:, 1].sum()
    total = bid_volume + ask_volume
    imbalance = (bid_volume - ask_volume) / total if total else 0

    spread = best_ask - best_bid
    spread_pct = spread / mid * 100 if mid else 0

    bid_threshold = np.mean(bids[:, 1]) * 3
    ask_threshold = np.mean(asks[:, 1]) * 3
    bid_walls = [
        {"price": float(price), "quantity": float(qty), "value": float(price * qty)}
        for price, qty in bids if qty >= bid_threshold
    ]
    ask_walls = [
        {"price": float(price), "quantity": float(qty), "value": float(price * qty)}
        for price, qty in asks if qty >= ask_threshold
    ]

    return {
        "symbol": book.get("symbol", ""),
        "mid_price": float(mid),
        "spread": float(spread),
        "spread_percent": float(spread_pct),
        "bid_volume": float(bid_volume),
        "ask_volume": float(ask_volume),
        "imbalance": float(imbalance),
        "bid_depth_usdt": float((bids[:, 0] * bids[:, 1]).sum()),
        "ask_depth_usdt": float((asks[:, 0] * asks[:, 1]).sum()),
        "bid_walls": bid_walls,
        "ask_walls": ask_walls,
    }


if __name__ == "__main__":
    os.makedirs("data/analysis", exist_ok=True)
    for path in glob.glob("data/raw/*orderbook.json"):
        with open(path) as file:
            book = json.load(file)
        result = analyze_orderbook(book)
        output = os.path.join("data/analysis", os.path.basename(path))
        with open(output, "w") as file:
            json.dump(result, file, indent=2)
        print(
            f"{result['symbol']} | Imbalance: {result['imbalance']:.3f} | "
            f"Spread: {result['spread_percent']:.5f}% | "
            f"Bid walls: {len(result['bid_walls'])} | "
            f"Ask walls: {len(result['ask_walls'])}"
        )
    print("Order book analysis completed.")
