import time
from datetime import datetime, timezone

import pandas as pd
import requests

from core.orderbook import analyze_orderbook


class BinanceMarketData:
    BASE_URLS = {
        "spot": "https://api.binance.com",
        "futures": "https://fapi.binance.com",
    }

    CANDLE_COLUMNS = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_buy_base", "taker_buy_quote", "ignore",
    ]

    def __init__(self, timeout=12):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "AI-Trader-MarketData/1.0"
        })

    def _request(self, market, endpoint, params):
        market = market.lower()

        if market not in self.BASE_URLS:
            raise ValueError("Market must be spot or futures")

        url = self.BASE_URLS[market] + endpoint
        response = self.session.get(
            url, params=params, timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def fetch_candles(
        self, market, symbol, interval="1m",
        limit=500, closed_only=True
    ):
        if not 2 <= int(limit) <= 1000:
            raise ValueError("limit must be between 2 and 1000")

        raw = self._request(
            market,
            "/api/v3/klines" if market == "spot"
            else "/fapi/v1/klines",
            {
                "symbol": symbol.upper(),
                "interval": interval,
                "limit": int(limit),
            },
        )

        if not isinstance(raw, list) or not raw:
            raise RuntimeError("Binance returned no candle data")

        df = pd.DataFrame(raw, columns=self.CANDLE_COLUMNS)

        numeric = [
            "open", "high", "low", "close", "volume",
            "quote_volume", "trades",
            "taker_buy_base", "taker_buy_quote",
        ]

        for column in numeric:
            df[column] = pd.to_numeric(
                df[column], errors="coerce"
            )

        df["open_time"] = pd.to_datetime(
            df["open_time"], unit="ms", utc=True
        )
        df["close_time"] = pd.to_datetime(
            df["close_time"], unit="ms", utc=True
        )

        now = pd.Timestamp.now(tz="UTC")
        df["is_closed"] = df["close_time"] < now

        df = df.dropna(
            subset=["open", "high", "low", "close", "volume"]
        ).reset_index(drop=True)

        if closed_only:
            df = df[df["is_closed"]].reset_index(drop=True)

        if len(df) < 2:
            raise RuntimeError("Not enough closed candles")

        df.attrs["market"] = market
        df.attrs["symbol"] = symbol.upper()
        df.attrs["interval"] = interval
        df.attrs["source"] = "binance_rest"
        df.attrs["received_at"] = datetime.now(
            timezone.utc
        ).isoformat()

        return df

    def fetch_orderbook(self, market, symbol, limit=100):
        raw = self._request(
            market,
            "/api/v3/depth" if market == "spot"
            else "/fapi/v1/depth",
            {
                "symbol": symbol.upper(),
                "limit": int(limit),
            },
        )

        if not raw.get("bids") or not raw.get("asks"):
            raise RuntimeError("Empty order book")

        book = {
            "symbol": symbol.upper(),
            "bids": raw["bids"],
            "asks": raw["asks"],
        }

        result = analyze_orderbook(book)
        result.update({
            "available": True,
            "market": market,
            "source": "binance_rest",
            "last_update_id": raw.get("lastUpdateId"),
            "received_at": datetime.now(
                timezone.utc
            ).isoformat(),
        })

        return result

    def fetch_book_ticker(self, market, symbol):
        market = str(market).strip().lower()
        symbol = str(symbol).strip().upper()

        if market not in self.BASE_URLS:
            raise ValueError("Market must be spot or futures")
        if not symbol:
            raise ValueError("Symbol cannot be empty")

        endpoint = (
            "/api/v3/ticker/bookTicker"
            if market == "spot"
            else "/fapi/v1/ticker/bookTicker"
        )

        raw = self._request(
            market,
            endpoint,
            {"symbol": symbol},
        )

        if not isinstance(raw, dict):
            raise RuntimeError("Invalid Binance book ticker response")

        try:
            bid = float(raw["bidPrice"])
            ask = float(raw["askPrice"])
        except (KeyError, TypeError, ValueError):
            raise RuntimeError("Missing or invalid bid/ask prices")

        import math
        if not math.isfinite(bid) or not math.isfinite(ask):
            raise RuntimeError("Non-finite bid/ask prices")
        if bid <= 0 or ask <= 0:
            raise RuntimeError("Bid/ask prices must be positive")
        if bid > ask:
            raise RuntimeError("Crossed order book: bid exceeds ask")

        mid_price = (bid + ask) / 2
        spread = ask - bid

        return {
            "market": market,
            "symbol": symbol,
            "bid": bid,
            "ask": ask,
            "mid_price": mid_price,
            "spread": spread,
            "spread_percent": (spread / mid_price) * 100,
            "source": "binance_rest",
            "received_at": datetime.now(timezone.utc).isoformat(),
        }

    def fetch_snapshot(
        self, market, symbol, timeframes=None,
        candle_limit=500, orderbook_limit=100
    ):
        if timeframes is None:
            timeframes = ["1m", "5m", "15m", "1h"]

        candles = {}
        errors = {}

        for interval in timeframes:
            try:
                candles[interval] = self.fetch_candles(
                    market, symbol, interval, candle_limit
                )
            except Exception as error:
                errors[interval] = str(error)

        try:
            orderbook = self.fetch_orderbook(
                market, symbol, orderbook_limit
            )
        except Exception as error:
            orderbook = {
                "available": False,
                "error": str(error),
                "market": market,
                "symbol": symbol.upper(),
            }

        return {
            "market": market,
            "symbol": symbol.upper(),
            "candles": candles,
            "orderbook": orderbook,
            "errors": errors,
            "received_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }
