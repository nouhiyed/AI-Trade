"""Causal historical backtest for the sole V3 strategy.

Uses closed 1m triggers, closed higher-timeframe context, next-1m-open entries,
V3 stop/target levels, adverse taker fees/slippage, and V3 time exits.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.futures.agent import FuturesAgent
from agents.spot.agent import SpotAgent
from core.binance_market_data import BinanceMarketData
from core.market_data_engine import MarketDataEngine
from core.technical import analyze as analyze_technical

TIMEFRAMES = {
    "futures": ("1m", "5m", "15m"),
    "spot": ("1m", "5m", "15m", "1h", "4h"),
}
INTERVAL_MS = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000,
    "1h": 3_600_000, "4h": 14_400_000,
}
BASE_TIMEFRAME = "1m"
FEE_RATE = {"spot": 0.001, "futures": 0.0005}
SLIPPAGE_RATE = {"spot": 0.0005, "futures": 0.0005}
MIN_NET_RR = 1.5
RISK_FRACTION = 0.005
STARTING_CAPITAL = 10_000.0
MAX_NOTIONAL_MULTIPLE = 1.0


def _month_starts(start_dt, end_dt):
    current = start_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    while current < end_dt:
        yield current
        month = current.month + 1
        year = current.year + (1 if month == 13 else 0)
        current = current.replace(year=year, month=1 if month == 13 else month)


def _read_binance_archive(payload, symbol, timeframe):
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if not names:
            raise RuntimeError(f"Binance archive has no CSV: {symbol} {timeframe}")
        frame = pd.read_csv(
            io.BytesIO(archive.read(names[0])),
            header=None, names=BinanceMarketData.CANDLE_COLUMNS,
        )
    numeric = [
        "open_time", "close_time", "open", "high", "low", "close",
        "volume", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote",
    ]
    for column in numeric:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=[
        "open_time", "close_time", "open", "high", "low", "close", "volume",
    ])
    if not frame.empty and float(frame["open_time"].median()) > 1e14:
        frame["open_time"] /= 1000.0
        frame["close_time"] /= 1000.0
    frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    frame["close_time"] = pd.to_datetime(frame["close_time"], unit="ms", utc=True)
    frame["is_closed"] = True
    frame.attrs.update({"symbol": symbol, "interval": timeframe, "source": "binance_vision"})
    return frame


def download_history(market, symbol, timeframe, start_dt, end_dt, cache_dir, years):
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{market}_{symbol}_{timeframe}_{years}y.csv"
    start_ms, end_ms = int(start_dt.timestamp() * 1000), int(end_dt.timestamp() * 1000)
    step = INTERVAL_MS[timeframe]
    if path.exists():
        cached = pd.read_csv(path, parse_dates=["open_time", "close_time"])
        if len(cached) >= 210:
            cached_start = pd.Timestamp(cached["open_time"].iloc[0]).timestamp() * 1000
            cached_end = pd.Timestamp(cached["close_time"].iloc[-1]).timestamp() * 1000
            if cached_start <= start_ms + step and cached_end >= end_ms - 2 * step:
                mask = (
                    (pd.to_datetime(cached["open_time"], utc=True) >= start_dt)
                    & (pd.to_datetime(cached["open_time"], utc=True) < end_dt)
                )
                return cached[mask].reset_index(drop=True)

    market_path = "spot" if market == "spot" else "futures/um"
    pages = []
    for month_start in _month_starts(start_dt, end_dt):
        month = month_start.strftime("%Y-%m")
        filename = f"{symbol}-{timeframe}-{month}.zip"
        url = (
            f"https://data.binance.vision/data/{market_path}/monthly/klines/"
            f"{symbol}/{timeframe}/{filename}"
        )
        response = requests.get(
            url, timeout=60, headers={"User-Agent": "AI-Trader-V3-Backtest/1.0"}
        )
        if response.status_code == 404:
            # Newly listed pairs have no archive before their listing date.
            continue
        response.raise_for_status()
        pages.append(_read_binance_archive(response.content, symbol, timeframe))
        print(f"Downloaded {market} {symbol} {timeframe} {month}", flush=True)

    if not pages:
        raise RuntimeError(f"No Binance historical archives: {market} {symbol} {timeframe}")
    frame = (
        pd.concat(pages, ignore_index=True)
        .drop_duplicates(subset=["open_time"])
        .sort_values("open_time")
        .reset_index(drop=True)
    )
    mask = (
        (pd.to_datetime(frame["open_time"], utc=True) >= start_dt)
        & (pd.to_datetime(frame["open_time"], utc=True) < end_dt)
    )
    frame = frame[mask].reset_index(drop=True)
    if len(frame) < 210:
        raise RuntimeError(
            f"Insufficient Binance history: {market} {symbol} {timeframe} ({len(frame)} candles)"
        )
    frame.to_csv(path, index=False)
    return frame


def _times_ms(frame):
    return (
        pd.to_datetime(frame["close_time"], utc=True)
        .astype("int64").to_numpy() // 1_000_000
    )


def _funding_history(client, symbol, start_dt, end_dt):
    """Fetch every historical USD-M funding event for the tested interval."""
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    cursor = start_ms
    events = []
    while cursor < end_ms:
        page = client._request("futures", "/fapi/v1/fundingRate", {
            "symbol": symbol, "startTime": cursor, "endTime": end_ms, "limit": 1000,
        })
        if not isinstance(page, list) or not page:
            break
        events.extend(page)
        last = int(page[-1].get("fundingTime", 0))
        next_cursor = last + 1
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if len(page) < 1000:
            break
    return sorted(
        (int(item["fundingTime"]), float(item["fundingRate"]))
        for item in events
        if start_ms <= int(item.get("fundingTime", 0)) <= end_ms
    )


def _fill_entry(raw, direction, slip):
    return raw * (1.0 + slip if direction == "LONG" else 1.0 - slip)


def _fill_exit(raw, direction, slip):
    return raw * (1.0 - slip if direction == "LONG" else 1.0 + slip)


def _bar_hit(bar, direction, level, stop):
    op, high, low = float(bar["open"]), float(bar["high"]), float(bar["low"])
    if direction == "LONG":
        hit = low <= level if stop else high >= level
        if not hit:
            return False, None
        if (stop and op <= level) or (not stop and op >= level):
            return True, op
    else:
        hit = high >= level if stop else low <= level
        if not hit:
            return False, None
        if (stop and op >= level) or (not stop and op <= level):
            return True, op
    return True, level


def _net_rr(entry, stop, target, market):
    risk = abs(entry - stop) / entry
    reward = abs(target - entry) / entry
    round_trip = 2 * (FEE_RATE[market] + SLIPPAGE_RATE[market])
    net_risk, net_reward = risk + round_trip, reward - round_trip
    return net_reward / net_risk if net_risk > 0 else 0.0


def _close_position(position, raw_price, reason, market, equity, exit_time):
    direction = position["direction"]
    fill = _fill_exit(raw_price, direction, SLIPPAGE_RATE[market])
    quantity = position["quantity"]
    gross = (
        (fill - position["entry_fill"]) * quantity
        if direction == "LONG"
        else (position["entry_fill"] - fill) * quantity
    )
    fee = fill * quantity * FEE_RATE[market]
    net = gross - fee
    position["net_pnl"] += net
    position["fees"] += fee
    position["exit_fill"] = fill
    position["exit_reason"] = reason
    position["exit_time"] = exit_time
    position["net_r"] = (
        position["net_pnl"] / position["initial_risk_cash"]
        if position["initial_risk_cash"] > 0 else 0.0
    )
    equity += net
    return equity


def _metrics(trades, equity, max_drawdown, market, symbol, start, end):
    pnls = [float(item["net_pnl"]) for item in trades]
    wins = [value for value in pnls if value > 0]
    losses = [value for value in pnls if value < 0]
    gross_profit, gross_loss = sum(wins), abs(sum(losses))
    return {
        "symbol": symbol,
        "market": market,
        "strategy_version": "v3",
        "decision_timeframe": "1m closed trigger",
        "start": start,
        "end": end,
        "starting_capital": STARTING_CAPITAL,
        "ending_equity": round(equity, 4),
        "net_pnl": round(equity - STARTING_CAPITAL, 4),
        "net_return_pct": round((equity / STARTING_CAPITAL - 1) * 100, 4),
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(len(wins) / len(trades) * 100, 2) if trades else 0.0,
        "profit_factor": (
            round(gross_profit / gross_loss, 4)
            if gross_loss else (None if not gross_profit else "Infinity")
        ),
        "average_net_r": round(
            sum(float(item.get("net_r", 0)) for item in trades) / len(trades), 4
        ) if trades else 0.0,
        "total_fees": round(sum(float(item["fees"]) for item in trades), 4),
        "funding_net_cashflow": round(sum(float(item.get("funding_net_cashflow", 0)) for item in trades), 4),
        "max_drawdown_pct": round(max_drawdown * 100, 4),
        "cost_assumptions": {
            "taker_fee_per_side": FEE_RATE[market],
            "slippage_per_side": SLIPPAGE_RATE[market],
            "round_trip_estimate_pct": round(
                2 * (FEE_RATE[market] + SLIPPAGE_RATE[market]) * 100, 4
            ),
        },
        "limitations": [
            "Futures funding events are applied at published rates; the nearest 1m close approximates funding mark price.",
            "Market orders use fixed adverse taker slippage.",
            "Sizing is capped at 1x notional; leverage effects are excluded.",
            "Entries occur at the next 1m open after a closed 1m signal candle.",
            "If stop and target are both touched in one 1m candle, stop is assumed first.",
        ],
    }


def run_one(client, market, symbol, years, cache_dir):
    now = datetime.now(timezone.utc)
    end_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_index = end_dt.year * 12 + end_dt.month - 1 - years * 12
    start_dt = datetime(
        month_index // 12, month_index % 12 + 1, 1, tzinfo=timezone.utc
    )
    funding_events = _funding_history(client, symbol, start_dt, end_dt) if market == "futures" else []
    funding_index = 0
    prepared = {}
    for timeframe in TIMEFRAMES[market]:
        print(f"Downloading {market} {symbol} {timeframe}...", flush=True)
        raw = download_history(
            market, symbol, timeframe, start_dt, end_dt, cache_dir, years
        )
        print(f"Preparing {market} {symbol} {timeframe}: {len(raw)} candles", flush=True)
        prepared[timeframe] = analyze_technical(raw)

    base = prepared[BASE_TIMEFRAME]
    base_times = _times_ms(base)
    frame_times = {tf: _times_ms(frame) for tf, frame in prepared.items()}
    agent = FuturesAgent() if market == "futures" else SpotAgent()
    trades, position = [], None
    equity = peak = STARTING_CAPITAL
    max_drawdown = 0.0
    first_time = None

    for i in range(210, len(base)):
        bar = base.iloc[i]
        asof = int(base_times[i])
        bar_close = pd.Timestamp(bar["close_time"])
        bar_open = pd.Timestamp(bar["open_time"])
        if first_time is None:
            first_time = bar_close.isoformat()

        while funding_index < len(funding_events) and funding_events[funding_index][0] <= asof:
            funding_time_ms, funding_rate = funding_events[funding_index]
            if position is not None and funding_time_ms > position["opened_at_ms"]:
                direction_sign = 1.0 if position["direction"] == "LONG" else -1.0
                cashflow = -direction_sign * position["quantity"] * float(bar["close"]) * funding_rate
                position["funding_net_cashflow"] += cashflow
                position["net_pnl"] += cashflow
                equity += cashflow
            funding_index += 1

        if position is not None:
            direction = position["direction"]
            stop_hit, stop_price = _bar_hit(bar, direction, position["stop"], True)
            target_hit, target_price = _bar_hit(bar, direction, position["target"], False)
            if stop_hit:
                equity = _close_position(
                    position, stop_price, "STOP_LOSS", market, equity, bar_close.isoformat()
                )
                trades.append(position)
                position = None
            elif target_hit:
                equity = _close_position(
                    position, target_price, "TAKE_PROFIT", market, equity, bar_close.isoformat()
                )
                trades.append(position)
                position = None
            elif (
                bar_close.value // 1_000_000 - position["opened_at_ms"]
                >= position["max_hold_minutes"] * 60_000
            ):
                equity = _close_position(
                    position, float(bar["close"]), "TIME_EXIT",
                    market, equity, bar_close.isoformat(),
                )
                trades.append(position)
                position = None

        mark_equity = equity
        if position is not None:
            close = float(bar["close"])
            unrealized = (
                (close - position["entry_fill"]) * position["quantity"]
                if position["direction"] == "LONG"
                else (position["entry_fill"] - close) * position["quantity"]
            )
            mark_equity += unrealized
        peak = max(peak, mark_equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - mark_equity) / peak)

        if position is not None or i + 1 >= len(base):
            continue

        agent_data = {"symbol": symbol, "orderbook": {"available": False}}
        ready = True
        for timeframe in TIMEFRAMES[market]:
            count = int(np.searchsorted(frame_times[timeframe], asof, side="right"))
            if count < 210:
                ready = False
                break
            agent_data[timeframe] = prepared[timeframe].iloc[max(0, count - 220):count].copy()
        if not ready:
            continue

        signal = agent.analyze(agent_data)
        agent.signals.clear()
        if signal.get("strategy_version") != "v3":
            continue
        plan = signal.get("trade_plan") or {}
        if plan.get("success") is not True or plan.get("strategy_version") != "v3":
            continue
        raw_direction = str(signal.get("direction", "WAIT")).upper()
        if market == "futures":
            if raw_direction not in ("LONG", "SHORT"):
                continue
            direction = raw_direction
        else:
            if raw_direction != "BUY":
                continue
            direction = "LONG"

        next_bar = base.iloc[i + 1]
        raw_entry = float(next_bar["open"])
        planned_entry = float(plan["entry"])
        atr = float(plan.get("atr") or 0)
        if atr <= 0 or abs(raw_entry - planned_entry) > max(
            0.10 * atr, planned_entry * 0.0002
        ):
            continue

        entry_fill = _fill_entry(raw_entry, direction, SLIPPAGE_RATE[market])
        stop, target = float(plan["stop_loss"]), float(plan["take_profit"])
        if (
            direction == "LONG" and not stop < entry_fill < target
        ) or (
            direction == "SHORT" and not target < entry_fill < stop
        ):
            continue
        if _net_rr(entry_fill, stop, target, market) < MIN_NET_RR:
            continue

        risk_per_unit = abs(entry_fill - stop)
        if risk_per_unit <= 0:
            continue
        quantity = min(
            equity * RISK_FRACTION / risk_per_unit,
            equity * MAX_NOTIONAL_MULTIPLE / entry_fill,
        )
        if not math.isfinite(quantity) or quantity <= 0:
            continue
        entry_fee = entry_fill * quantity * FEE_RATE[market]
        equity -= entry_fee
        max_hold = int(plan.get("max_hold_minutes") or (12 if market == "futures" else 15))
        position = {
            "symbol": symbol,
            "market": market,
            "strategy_version": "v3",
            "direction": direction,
            "timeframe": "1m",
            "entry_time": pd.Timestamp(next_bar["open_time"]).isoformat(),
            "opened_at_ms": int(pd.Timestamp(next_bar["open_time"]).value // 1_000_000),
            "entry_price": raw_entry,
            "entry_fill": entry_fill,
            "stop_loss": stop,
            "take_profit": target,
            "quantity": quantity,
            "initial_risk_cash": risk_per_unit * quantity,
            "max_hold_minutes": max_hold,
            "net_pnl": -entry_fee,
            "fees": entry_fee,
            "funding_net_cashflow": 0.0,
            "exit_time": None,
            "exit_fill": None,
            "exit_reason": "OPEN",
            "net_r": 0.0,
            "net_reward_risk_at_entry": _net_rr(entry_fill, stop, target, market),
        }

    if position is not None:
        final_bar = base.iloc[-1]
        equity = _close_position(
            position, float(final_bar["close"]), "END_OF_DATA",
            market, equity, pd.Timestamp(final_bar["close_time"]).isoformat(),
        )
        trades.append(position)
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak)

    start_label = first_time or pd.Timestamp(base["close_time"].iloc[0]).isoformat()
    end_label = pd.Timestamp(base["close_time"].iloc[-1]).isoformat()
    return _metrics(trades, equity, max_drawdown, market, symbol, start_label, end_label), trades


def main():
    parser = argparse.ArgumentParser(description="All-pair historical backtest for AI-Trader V3")
    parser.add_argument("--years", type=int, choices=(1, 2, 3), default=2)
    parser.add_argument("--symbols", nargs="+", default=None,
                        help="Optional explicit symbol list; default scans every eligible pair")
    parser.add_argument("--output", default="backtest_results")
    parser.add_argument("--cache", default="data/backtest_cache")
    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    client = BinanceMarketData()
    all_summaries, all_trades, failures = [], [], []
    universes = {
        market: (args.symbols if args.symbols else client.fetch_symbols(market))
        for market in ("futures", "spot")
    }

    for market in ("futures", "spot"):
        symbols = universes[market]
        print(f"\n========== {market.upper()}: {len(symbols)} eligible pairs ==========", flush=True)
        for number, symbol in enumerate(symbols, 1):
            print(f"\n[{number}/{len(symbols)}] {market.upper()} {symbol}", flush=True)
            try:
                metrics, trades = run_one(
                    client, market, symbol, args.years, Path(args.cache)
                )
                all_summaries.append(metrics)
                all_trades.extend(trades)
                pair_dir = output / market / symbol
                pair_dir.mkdir(parents=True, exist_ok=True)
                (pair_dir / "summary.json").write_text(
                    json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                pd.DataFrame(trades).to_csv(pair_dir / "trades.csv", index=False)
                print(json.dumps(metrics, ensure_ascii=False), flush=True)
            except Exception as error:
                failure = {"market": market, "symbol": symbol, "error": str(error)}
                failures.append(failure)
                print("PAIR FAILED: " + json.dumps(failure, ensure_ascii=False), flush=True)

            (output / "progress.json").write_text(json.dumps({
                "years_requested": args.years,
                "completed_pairs": len(all_summaries),
                "failed_pairs": len(failures),
                "symbols_by_market": {key: len(value) for key, value in universes.items()},
                "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            }, ensure_ascii=False, indent=2), encoding="utf-8")

    report = {
        "engine": "production_agents_v3_only",
        "strategy_version": "v3",
        "years_requested": args.years,
        "symbols_by_market": {key: list(value) for key, value in universes.items()},
        "completed_pairs": len(all_summaries),
        "failed_pairs": failures,
        "results": all_summaries,
    }
    (output / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    pd.DataFrame(all_trades).to_csv(output / "trades.csv", index=False)
    print(f"ALL V3 BACKTESTS FINISHED: {output / 'summary.json'}", flush=True)


if __name__ == "__main__":
    main()
