import os
from core.binance_market_data import BinanceMarketData


class FuturesMarketScanner:
    def __init__(self, timeout=6):
        self.market = BinanceMarketData(timeout=timeout, total_timeout=timeout)

    def scan_universe(self, limit=12, min_quote_volume=None):
        limit = max(1, min(int(limit), 30))
        minimum = float(
            min_quote_volume
            if min_quote_volume is not None
            else os.getenv("FUTURES_MIN_QUOTE_VOLUME", "5000000")
        )

        exchange = self.market._request(
            "futures", "/fapi/v1/exchangeInfo", {}
        )
        tickers = self.market._request(
            "futures", "/fapi/v1/ticker/24hr", {}
        )

        eligible = {
            item["symbol"]
            for item in exchange.get("symbols", [])
            if item.get("status") == "TRADING"
            and item.get("contractType") == "PERPETUAL"
            and item.get("quoteAsset") == "USDT"
            and item.get("symbol")
        }

        ranked = []
        for item in tickers:
            symbol = item.get("symbol")
            if symbol not in eligible:
                continue
            try:
                volume = float(item.get("quoteVolume", 0))
                price = float(item.get("lastPrice", 0))
                change = float(item.get("priceChangePercent", 0))
            except (TypeError, ValueError):
                continue

            if volume < minimum or price <= 0:
                continue

            ranked.append({
                "symbol": symbol,
                "quote_volume": volume,
                "last_price": price,
                "change_24h_percent": change,
            })

        ranked.sort(
            key=lambda item: item["quote_volume"],
            reverse=True
        )
        return ranked[:limit]
