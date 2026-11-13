"""Transparent, candle-derived execution-cost estimates for research backtests.

Spread and slippage are estimates, not observed historical quotes. Funding is
loaded from Binance's public USD-M futures funding-rate history.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import requests


class BacktestCostModel:
    def __init__(self, market: str):
        if market not in ("spot", "futures"):
            raise ValueError("market must be spot or futures")
        self.market = market

    @staticmethod
    def _number(bar, key, default=0.0):
        try:
            value = float(bar.get(key, default))
            return value if math.isfinite(value) else default
        except (TypeError, ValueError, AttributeError):
            return default

    def components(self, bar):
        close = self._number(bar, "close")
        atr = self._number(bar, "ATR", self._number(bar, "atr"))
        quote_volume = self._number(bar, "quote_volume")
        if quote_volume <= 0:
            volume = self._number(bar, "volume")
            quote_volume = close * volume
        if close <= 0:
            raise ValueError("A positive close is required for execution-cost estimation")

        volatility_bps = max(0.0, atr / close * 10000.0) if atr > 0 else 0.0
        liquidity_units = max(0.05, quote_volume / 1_000_000.0)
        liquidity_penalty = 1.0 / math.sqrt(liquidity_units)

        # Half-spread and market-impact/slippage proxies, each capped.
        half_spread_bps = min(12.0, 0.5 + 0.025 * volatility_bps + 0.8 * liquidity_penalty)
        slippage_bps = min(25.0, 1.0 + 0.10 * volatility_bps + 2.0 * liquidity_penalty)
        return {
            "half_spread_rate": half_spread_bps / 10000.0,
            "slippage_rate": slippage_bps / 10000.0,
            "total_adverse_rate": (half_spread_bps + slippage_bps) / 10000.0,
            "spread_bps_estimated": half_spread_bps,
            "slippage_bps_estimated": slippage_bps,
            "cost_source": "OHLCV_VOLATILITY_LIQUIDITY_PROXY",
        }


def load_funding_history(symbol, start_ms, end_ms, cache_dir="data/funding_cache"):
    """Return complete Binance USD-M funding events in [start_ms, end_ms].

    Raises on retrieval failure; missing funding is never silently treated as zero.
    """
    folder = Path(cache_dir)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{symbol}_{start_ms}_{end_ms}.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("complete") is True:
            return payload["events"]

    events, cursor = [], int(start_ms)
    url = "https://fapi.binance.com/fapi/v1/fundingRate"
    while cursor <= end_ms:
        response = requests.get(
            url,
            params={"symbol": symbol, "startTime": cursor, "endTime": int(end_ms), "limit": 1000},
            timeout=30,
            headers={"User-Agent": "AI-Trader-Research/2.0"},
        )
        response.raise_for_status()
        batch = response.json()
        if not isinstance(batch, list):
            raise RuntimeError("Unexpected Binance funding-rate response")
        if not batch:
            break
        for item in batch:
            events.append({
                "funding_time": int(item["fundingTime"]),
                "funding_rate": float(item["fundingRate"]),
            })
        next_cursor = events[-1]["funding_time"] + 1
        if next_cursor <= cursor:
            raise RuntimeError("Binance funding pagination did not advance")
        cursor = next_cursor
        if len(batch) < 1000:
            break

    events.sort(key=lambda x: x["funding_time"])
    if any(not math.isfinite(x["funding_rate"]) for x in events):
        raise RuntimeError("Non-finite funding rate returned by Binance")
    path.write_text(json.dumps({"complete": True, "events": events}), encoding="utf-8")
    return events


def apply_funding(position, funding_rate, mark_price):
    """Return signed funding cashflow; positive means credited to the account."""
    if position["market"] != "futures":
        return 0.0
    quantity = float(position.get("remaining_quantity", 0.0))
    notional = abs(float(mark_price) * quantity)
    direction_sign = 1.0 if str(position["direction"]).upper() == "LONG" else -1.0
    return -direction_sign * float(funding_rate) * notional
