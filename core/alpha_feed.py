"""Binance Alpha token feed: prices, liquidity gates and contract info.

Alpha tokens are traded against USDT through Binance's own routing; there is no
public order book, so the DEMO uses the token price plus an extra slippage
allowance (thin liquidity) on both sides.
"""
import os
import threading
import time

import requests

TOKEN_LIST = (
    "https://www.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/cex/"
    "alpha/all/token/list"
)


def _f(value, default=None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number and abs(number) != float("inf") else default


class AlphaFeed:

    EXTRA_SLIPPAGE = float(os.getenv("ALPHA_EXTRA_SLIPPAGE", "0.003"))

    def __init__(self, session=None, timeout=8, ttl=3.0, clock=time.time,
                 min_liquidity=None, min_volume=None):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": "AI-Trader-Alpha/1.0"})
        self.timeout = timeout
        self.ttl = ttl
        self.clock = clock
        self.min_liquidity = float(
            min_liquidity if min_liquidity is not None
            else os.getenv("ALPHA_MIN_LIQUIDITY", "300000"))
        self.min_volume = float(
            min_volume if min_volume is not None
            else os.getenv("ALPHA_MIN_VOLUME", "1000000"))
        self._lock = threading.Lock()
        self._cache = None

    def _tokens(self):
        now = self.clock()
        with self._lock:
            if self._cache and now - self._cache[0] < self.ttl:
                return self._cache[1]
        r = self.session.get(TOKEN_LIST, timeout=self.timeout)
        r.raise_for_status()
        payload = r.json()
        if not isinstance(payload, dict) or payload.get("success") is False:
            raise RuntimeError("Alpha token list request was not successful")
        rows = {}
        for token in payload.get("data") or []:
            if not isinstance(token, dict):
                continue
            alpha_id = str(token.get("alphaId") or "").strip()
            price = _f(token.get("price"))
            if not alpha_id or not price or price <= 0:
                continue
            symbol = alpha_id.upper() + "USDT"
            ticker = str(token.get("symbol") or "").strip().upper()
            token_name = str(
                token.get("name")
                or token.get("tokenName")
                or token.get("cexCoinName")
                or ticker
                or alpha_id
            ).strip()
            rows[symbol] = {
                "symbol": symbol,
                "name": token_name,
                "ticker": ticker,
                "display": ticker or token_name.upper(),
                "price": price,
                "volume_24h": _f(token.get("volume24h"), 0.0),
                "liquidity": _f(token.get("liquidity"), 0.0),
                "change_24h": _f(token.get("percentChange24h"), 0.0),
                "chain_id": str(token.get("chainId") or ""),
                "address": str(token.get("contractAddress") or ""),
                "offline": bool(token.get("offline") or token.get("offsell")),
            }
        with self._lock:
            self._cache = (now, rows)
        return rows

    def symbols(self):
        """Return Binance Alpha token names and symbols for the mobile selector."""
        items = []
        for row in self._tokens().values():
            items.append({
                "symbol": row["symbol"],
                "name": row.get("name") or row.get("display") or row["symbol"],
                "display": row.get("display") or row["symbol"],
                "ticker": row.get("ticker") or row.get("display") or "",
                "chain_id": row.get("chain_id", ""),
                "price": row.get("price"),
                "volume_24h": row.get("volume_24h", 0.0),
                "liquidity": row.get("liquidity", 0.0),
                "change_24h": row.get("change_24h", 0.0),
                "offline": row.get("offline", False),
            })
        return sorted(items, key=lambda item: (str(item["name"]).casefold(), item["symbol"]))

    def token(self, symbol):
        row = self._tokens().get(str(symbol).upper())
        if row is None:
            raise KeyError("Unknown Alpha symbol: " + str(symbol))
        return row

    def price(self, symbol):
        row = self.token(symbol)
        if row["offline"]:
            raise ValueError("Alpha token is offline")
        return row["price"]

    def universe(self, limit=10):
        """Liquid, online Alpha tokens ranked by 24h volume."""
        rows = [r for r in self._tokens().values()
                if not r["offline"]
                and r["liquidity"] >= self.min_liquidity
                and r["volume_24h"] >= self.min_volume]
        rows.sort(key=lambda r: r["volume_24h"], reverse=True)
        return rows[: max(1, int(limit))]
