import json
import os
import glob
import numpy as np

def analyze_orderbook(book):
    bids = np.array(book["bids"], dtype=float)
    asks = np.array(book["asks"], dtype=float)

    best_bid = bids[0, 0]
    best_ask = asks[0, 0]
    mid = (best_bid + best_ask) / 2

    bid_volume = bids[:, 1].sum()
    ask_volume = asks[:, 1].sum()

    total = bid_volume + ask_volume

    imbalance = (
        (bid_volume - ask_volume) / total
        if total else 0
    )

    spread = best_ask - best_bid
    spread_pct = spread / mid * 100

    bid_walls = []
    ask_walls = []

    bid_threshold = np.mean(bids[:, 1]) * 3
    ask_threshold = np.mean(asks[:, 1]) * 3

    for price, qty in bids:
        if qty >= bid_threshold:
            bid_walls.append({
                "price": float(price),
                "quantity": float(qty),
                "value": float(price * qty)
            })

    for price, qty in asks:
        if qty >= ask_threshold:
            ask_walls.append({
                "price": float(price),
                "quantity": float(qty),
                "value": float(price * qty)
            })

    bid_depth = bids[:, 0] * bids[:, 1]
    ask_depth = asks[:, 0] * asks[:, 1]

    return {
        "symbol": book["symbol"],
        "mid_price": float(mid),
        "spread": float(spread),
        "spread_percent": float(spread_pct),
        "bid_volume": float(bid_volume),
        "ask_volume": float(ask_volume),
        "imbalance": float(imbalance),
        "bid_depth_usdt": float(bid_depth.sum()),
        "ask_depth_usdt": float(ask_depth.sum()),
        "bid_walls": bid_walls,
        "ask_walls": ask_walls
    }


if __name__ == "__main__":
    os.makedirs("data/analysis", exist_ok=True)

    for path in glob.glob("data/raw/*orderbook.json"):
        with open(path) as f:
            book = json.load(f)

        result = analyze_orderbook(book)

        output = (
            "data/analysis/" +
            os.path.basename(path)
        )

        with open(output, "w") as f:
            json.dump(result, f, indent=2)

        print(
            f"{result['symbol']} | "
            f"Imbalance: {result['imbalance']:.3f} | "
            f"Spread: {result['spread_percent']:.5f}% | "
            f"Bid walls: {len(result['bid_walls'])} | "
            f"Ask walls: {len(result['ask_walls'])}"
        )

    print("Order book analysis completed.")

