"""Transparent, candle-derived execution-cost estimates for research backtests.

Spread and slippage are estimates, not observed historical quotes. Funding is
loaded from Binance USD-M history, preferring REST and falling back to the
official Binance Vision monthly archive when REST is unavailable.
"""
from __future__ import annotations

import csv
import io
import json
import math
import zipfile
from datetime import datetime, timezone
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


def _month_starts_ms(start_ms, end_ms):
    current = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc)
    current = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc)
    while current < end:
        yield current
        month = current.month + 1
        current = current.replace(year=current.year + (month == 13),
                                 month=1 if month == 13 else month)


def _funding_timestamp(value):
    timestamp = int(float(value))
    # Binance Vision has used milliseconds and, in some newer exports,
    # microseconds. Normalise both to the REST endpoint's milliseconds.
    if timestamp > 10**14:
        timestamp //= 1000
    elif timestamp < 10**11:
        timestamp *= 1000
    return timestamp


def _load_funding_from_vision(symbol, start_ms, end_ms):
    events = []
    for month in _month_starts_ms(start_ms, end_ms):
        label = month.strftime("%Y-%m")
        filename = f"{symbol}-fundingRate-{label}.zip"
        url = (
            "https://data.binance.vision/data/futures/um/monthly/"
            f"fundingRate/{symbol}/{filename}"
        )
        response = requests.get(
            url, timeout=60, headers={"User-Agent": "AI-Trader-Research/2.0"}
        )
        if response.status_code == 404:
            raise RuntimeError(
                f"Binance Vision funding archive missing for {symbol} {label}; "
                "funding cannot be assumed to be zero"
            )
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if not csv_names:
                raise RuntimeError(f"Funding archive has no CSV: {symbol} {label}")
            with archive.open(csv_names[0]) as stream:
                rows = csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig"))
                for row in rows:
                    lowered = {str(k).strip().lower(): v for k, v in row.items() if k}
                    time_value = next(
                        (lowered[k] for k in ("fundingtime", "funding_time", "calc_time", "timestamp")
                         if lowered.get(k) not in (None, "")),
                        None,
                    )
                    rate_value = next(
                        (lowered[k] for k in ("fundingrate", "funding_rate", "last_funding_rate", "rate")
                         if lowered.get(k) not in (None, "")),
                        None,
                    )
                    if time_value is None or rate_value is None:
                        raise RuntimeError(
                            f"Unrecognised funding CSV columns for {symbol} {label}: "
                            f"{list(lowered)}"
                        )
                    funding_time = _funding_timestamp(time_value)
                    if start_ms <= funding_time <= end_ms:
                        events.append({
                            "funding_time": funding_time,
                            "funding_rate": float(rate_value),
                        })

    events.sort(key=lambda x: x["funding_time"])
    deduplicated = {event["funding_time"]: event for event in events}
    result = list(deduplicated.values())
    if any(not math.isfinite(x["funding_rate"]) for x in result):
        raise RuntimeError("Non-finite funding rate returned by Binance Vision")
    return result


def load_funding_history(symbol, start_ms, end_ms, cache_dir="data/funding_cache"):
    """Return complete Binance USD-M funding events in [start_ms, end_ms].

    REST is preferred. On REST/network failure, the official Binance Vision
    monthly funding archives are used. Missing funding is never silently zero.
    """
    folder = Path(cache_dir)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{symbol}_{start_ms}_{end_ms}.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("complete") is True and payload.get("events") is not None:
            return payload["events"]

    events, cursor = [], int(start_ms)
    url = "https://fapi.binance.com/fapi/v1/fundingRate"
    try:
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
        source = "BINANCE_FAPI_REST"
    except (requests.RequestException, RuntimeError, ValueError, KeyError):
        # Discard any partial REST page set: fallback must cover the full range.
        events = _load_funding_from_vision(symbol, int(start_ms), int(end_ms))
        source = "BINANCE_VISION_MONTHLY_ARCHIVE"

    events.sort(key=lambda x: x["funding_time"])
    if any(not math.isfinite(x["funding_rate"]) for x in events):
        raise RuntimeError("Non-finite funding rate returned by Binance")
    path.write_text(
        json.dumps({"complete": True, "source": source, "events": events}),
        encoding="utf-8",
    )
    print(f"Loaded {len(events)} {symbol} funding events from {source}", flush=True)
    return events


def apply_funding(position, funding_rate, mark_price):
    """Return signed funding cashflow; positive means credited to the account."""
    if position["market"] != "futures":
        return 0.0
    quantity = float(position.get("remaining_quantity", 0.0))
    notional = abs(float(mark_price) * quantity)
    direction_sign = 1.0 if str(position["direction"]).upper() == "LONG" else -1.0
    return -direction_sign * float(funding_rate) * notional
