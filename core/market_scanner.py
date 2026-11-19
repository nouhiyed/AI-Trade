import os
from core.binance_market_data import BinanceMarketData


class FuturesMarketScanner:
    def __init__(self, timeout=6):
        self.market = BinanceMarketData(timeout=timeout, total_timeout=timeout)

    def scan_universe(self, limit=None, min_quote_volume=None):
        """Return every active USDT perpetual by default.

        Optional limit and min_quote_volume are only for explicit narrowed scans.
        Automatic scanning passes neither, so rank and volume never exclude a pair.
        """
        limit = 30 if limit is None else max(1, min(30, int(limit)))
        minimum = float(min_quote_volume) if min_quote_volume is not None else None

        exchange = self.market._request("futures", "/fapi/v1/exchangeInfo", {})
        tickers = self.market._request("futures", "/fapi/v1/ticker/24hr", {})

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
            if price <= 0:
                continue
            if minimum is not None and volume < minimum:
                continue
            ranked.append({
                "symbol": symbol,
                "quote_volume": volume,
                "last_price": price,
                "change_24h_percent": change,
            })

        ranked.sort(key=lambda item: item["quote_volume"], reverse=True)
        return ranked[:limit]
