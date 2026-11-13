"""Causal per-coin historical backtest; each coin produces independent Futures and Spot reports."""
from __future__ import annotations
import argparse
import io
import json
import math
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from agents.futures.agent import FuturesAgent
from agents.spot.agent import SpotAgent
from core.binance_market_data import BinanceMarketData
from core.market_data_engine import MarketDataEngine
from core.trade_planner import TradePlanner
from core.trailing_stop import calculate_trailing_stop
from core.backtest_costs import BacktestCostModel, load_funding_history, apply_funding

SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT", "LINKUSDT")
TIMEFRAMES = {
    "futures": ("1m", "5m", "15m", "1h"),
    "spot": ("5m", "15m", "1h", "4h"),
}
INTERVAL_MS = {"1m": 60000, "5m": 300000, "15m": 900000, "1h": 3600000, "4h": 14400000}
FEE_RATE = {"spot": 0.001, "futures": 0.0005}
SLIPPAGE_RATE = {"spot": 0.0005, "futures": 0.0005}
BASE_TIMEFRAME = "5m"
STARTING_CAPITAL = 10000.0
MAX_NOTIONAL_MULTIPLE = 1.0
RISK_FRACTION = 0.0025  # matched risk for fair comparison
_CURRENT_EXECUTION_COMPONENTS = {"half_spread_rate": 0.0, "slippage_rate": 0.0}


def _month_starts(start_dt, end_dt):
    current = start_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    while current < end_dt:
        yield current
        month = current.month + 1
        year = current.year + (1 if month == 13 else 0)
        current = current.replace(year=year, month=1 if month == 13 else month)


def _read_binance_archive(payload, symbol, timeframe):
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if not csv_names:
            raise RuntimeError(f"Binance archive has no CSV: {symbol} {timeframe}")
        frame = pd.read_csv(
            io.BytesIO(archive.read(csv_names[0])),
            header=None, names=BinanceMarketData.CANDLE_COLUMNS,
        )
    numeric = [
        "open_time", "close_time", "open", "high", "low", "close",
        "volume", "quote_volume", "trades", "taker_buy_base",
        "taker_buy_quote",
    ]
    for column in numeric:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["open_time", "close_time", "open", "high", "low", "close", "volume"])
    # Binance Vision archives use microsecond timestamps for newer data sets.
    if not frame.empty and float(frame["open_time"].median()) > 1e14:
        frame["open_time"] = frame["open_time"] / 1000.0
        frame["close_time"] = frame["close_time"] / 1000.0
    frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    frame["close_time"] = pd.to_datetime(frame["close_time"], unit="ms", utc=True)
    frame["is_closed"] = True
    frame.attrs.update({"symbol": symbol, "interval": timeframe, "source": "binance_vision"})
    return frame


def download_history(market, symbol, timeframe, start_dt, end_dt, cache_dir, years):
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{market}_{symbol}_{timeframe}_{years}y.csv"
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    step = INTERVAL_MS[timeframe]
    if path.exists():
        cached = pd.read_csv(path, parse_dates=["open_time", "close_time"])
        if len(cached) >= 210:
            cached_start = pd.Timestamp(cached["open_time"].iloc[0]).timestamp() * 1000
            cached_end = pd.Timestamp(cached["close_time"].iloc[-1]).timestamp() * 1000
            if cached_start <= start_ms + step and cached_end >= end_ms - 2 * step:
                return cached[
                    (pd.to_datetime(cached["open_time"], utc=True) >= start_dt)
                    & (pd.to_datetime(cached["open_time"], utc=True) < end_dt)
                ].reset_index(drop=True)

    market_path = "spot" if market == "spot" else "futures/um"
    pages = []
    for month_start in _month_starts(start_dt, end_dt):
        month = month_start.strftime("%Y-%m")
        filename = f"{symbol}-{timeframe}-{month}.zip"
        url = f"https://data.binance.vision/data/{market_path}/monthly/klines/{symbol}/{timeframe}/{filename}"
        response = requests.get(url, timeout=60, headers={"User-Agent": "AI-Trader-Backtest/1.0"})
        if response.status_code == 404:
            raise RuntimeError(f"Missing Binance historical archive: {market} {symbol} {timeframe} {month}")
        response.raise_for_status()
        pages.append(_read_binance_archive(response.content, symbol, timeframe))
        print(f"Downloaded {market} {symbol} {timeframe} {month}", flush=True)

    if not pages:
        raise RuntimeError(f"No Binance archive data: {market} {symbol} {timeframe}")
    frame = (pd.concat(pages, ignore_index=True)
             .drop_duplicates(subset=["open_time"])
             .sort_values("open_time").reset_index(drop=True))
    frame = frame[
        (pd.to_datetime(frame["open_time"], utc=True) >= start_dt)
        & (pd.to_datetime(frame["open_time"], utc=True) < end_dt)
    ].reset_index(drop=True)
    if len(frame) < 210:
        raise RuntimeError(f"Insufficient Binance archive candles: {market} {symbol} {timeframe} ({len(frame)})")
    frame.to_csv(path, index=False)
    return frame


def _times_ms(frame):
    return (pd.to_datetime(frame["close_time"], utc=True)
            .astype("int64").to_numpy() // 1000000)


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


def _close_quantity(position, raw_price, quantity, reason, market, equity):
    direction = position["direction"]
    exit_fill = _fill_exit(raw_price, direction, SLIPPAGE_RATE[market])
    components = _CURRENT_EXECUTION_COMPONENTS
    position["spread_cost"] = position.get("spread_cost", 0.0) + raw_price * quantity * components["half_spread_rate"]
    position["slippage_cost"] = position.get("slippage_cost", 0.0) + raw_price * quantity * components["slippage_rate"]
    gross = ((exit_fill - position["entry_fill"]) * quantity if direction == "LONG"
             else (position["entry_fill"] - exit_fill) * quantity)
    fee = exit_fill * quantity * FEE_RATE[market]
    position["net_pnl"] += gross - fee
    position["fees"] += fee
    position["remaining_quantity"] -= quantity
    position["exit_fill"] = exit_fill
    position["last_exit_reason"] = reason
    return equity + gross - fee


def _finalize(position, trades):
    trades.append({
        "symbol": position["symbol"], "market": position["market"],
        "direction": position["direction"], "timeframe": position["timeframe"],
        "entry_time": position["entry_time"], "exit_time": position["last_exit_time"],
        "entry_price": position["entry_fill"], "last_exit_price": position.get("exit_fill"),
        "stop_loss": position["initial_stop"], "take_profit": position["initial_target"],
        "strategy": position["strategy"], "net_pnl": position["net_pnl"],
        "fees": position["fees"],
        "spread_cost_estimated": position.get("spread_cost", 0.0),
        "slippage_cost_estimated": position.get("slippage_cost", 0.0),
        "funding_pnl": position.get("funding_pnl", 0.0),
        "funding_settlements": position.get("funding_settlements", 0),
        "mae_pct": round(position.get("mae_pct", 0.0) * 100, 4),
        "mfe_pct": round(position.get("mfe_pct", 0.0) * 100, 4),
        "holding_minutes": round((pd.Timestamp(position["last_exit_time"]) - pd.Timestamp(position["entry_time"])).total_seconds() / 60.0, 2),
        "exit_reason": position["last_exit_reason"],
    })


def _metrics(trades, equity, max_drawdown, market, symbol, start, end):
    pnls = [float(t["net_pnl"]) for t in trades]
    wins, losses = [p for p in pnls if p > 0], [p for p in pnls if p < 0]
    gross_profit, gross_loss = sum(wins), abs(sum(losses))
    return {
        "symbol": symbol, "market": market, "decision_timeframe": BASE_TIMEFRAME,
        "start": start, "end": end, "starting_capital": STARTING_CAPITAL,
        "ending_equity": round(equity, 4), "net_pnl": round(equity - STARTING_CAPITAL, 4),
        "net_return_pct": round((equity / STARTING_CAPITAL - 1) * 100, 4),
        "trades": len(trades), "wins": len(wins), "losses": len(losses),
        "win_rate_pct": round(len(wins) / len(trades) * 100, 2) if trades else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else (None if not gross_profit else "Infinity"),
        "average_trade_pnl": round(sum(pnls) / len(pnls), 4) if pnls else 0.0,
        "gross_profit": round(gross_profit, 4), "gross_loss": round(gross_loss, 4),
        "total_fees": round(sum(float(t["fees"]) for t in trades), 4),
        "total_funding_pnl": round(sum(float(t.get("funding_pnl", 0.0)) for t in trades), 4),
        "total_estimated_spread_cost": round(sum(float(t.get("spread_cost_estimated", 0.0)) for t in trades), 4),
        "total_estimated_slippage_cost": round(sum(float(t.get("slippage_cost_estimated", 0.0)) for t in trades), 4),
        "max_drawdown_pct": round(max_drawdown * 100, 4),
        "cost_assumptions": {
            "taker_fee_per_side": FEE_RATE[market],
            "execution_cost_model": "dynamic OHLCV volatility/liquidity proxy; half-spread plus slippage, capped",
            "funding_source": "Binance USD-M historical fundingRate endpoint for Futures",
            "funding_mark_price": "5m close proxy at settlement timestamp",
            "historical_spread_is_observed": False,
        },
        "limitations": [
            "Historical order-book imbalance is unavailable; agents run without the live order-book bonus.",
            "Futures funding is charged at historical Binance settlement timestamps; 5m close is the mark-price proxy.",
            "Spread and slippage are dynamic OHLCV volatility/liquidity proxies, not observed historical quotes.",
            "Sizing is capped at 1x notional to isolate strategy performance from leverage.",
            "Signals use closed 5m candles and enter at the next 5m open.",
            "If stop and target are both touched in one candle, stop is assumed first.",
        ],
    }


def run_one(client, market_engine, planner, market, symbol, years, cache_dir):
    now = datetime.now(timezone.utc)
    end_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_index = end_dt.year * 12 + end_dt.month - 1 - years * 12
    start_dt = datetime(month_index // 12, month_index % 12 + 1, 1, tzinfo=timezone.utc)
    prepared = {}
    for tf in TIMEFRAMES[market]:
        print(f"Downloading {market} {symbol} {tf}...", flush=True)
        raw = download_history(market, symbol, tf, start_dt, end_dt, cache_dir, years)
        print(f"Preparing {market} {symbol} {tf}: {len(raw)} candles", flush=True)
        prepared[tf] = market_engine._prepare_frame(raw, symbol, market, tf)

    base = prepared[BASE_TIMEFRAME]
    cost_model = BacktestCostModel(market)
    funding_events = (load_funding_history(symbol, int(start_dt.timestamp() * 1000),
                       int(end_dt.timestamp() * 1000), cache_dir.parent / "funding_cache")
                      if market == "futures" else [])
    funding_times = [int(x["funding_time"]) for x in funding_events]
    funding_cursor = 0
    base_times = _times_ms(base)
    frame_times = {tf: _times_ms(frame) for tf, frame in prepared.items()}
    agent = FuturesAgent() if market == "futures" else SpotAgent()
    trades, position = [], None
    equity, peak, max_drawdown = STARTING_CAPITAL, STARTING_CAPITAL, 0.0
    first_time = None

    for i in range(210, len(base)):
        bar, asof = base.iloc[i], int(base_times[i])
        global _CURRENT_EXECUTION_COMPONENTS
        _CURRENT_EXECUTION_COMPONENTS = cost_model.components(bar)
        SLIPPAGE_RATE[market] = _CURRENT_EXECUTION_COMPONENTS["total_adverse_rate"]
        if first_time is None:
            first_time = pd.Timestamp(bar["close_time"]).isoformat()

        if position is not None:
            while funding_cursor < len(funding_events) and funding_times[funding_cursor] <= asof:
                event = funding_events[funding_cursor]
                if funding_times[funding_cursor] > position.get("entry_time_ms", 0):
                    cashflow = apply_funding(position, event["funding_rate"], float(bar["close"]))
                    position["funding_pnl"] += cashflow
                    position["funding_settlements"] += 1
                    position["net_pnl"] += cashflow
                    equity += cashflow
                funding_cursor += 1
            direction = position["direction"]
            entry_px = float(position["entry_fill"])
            high_px, low_px = float(bar["high"]), float(bar["low"])
            favorable = ((high_px - entry_px) / entry_px if direction == "LONG" else (entry_px - low_px) / entry_px)
            adverse = ((entry_px - low_px) / entry_px if direction == "LONG" else (high_px - entry_px) / entry_px)
            position["mfe_pct"] = max(position.get("mfe_pct", 0.0), favorable)
            position["mae_pct"] = max(position.get("mae_pct", 0.0), adverse)
            stop_hit, stop_price = _bar_hit(bar, direction, position["stop"], True)
            target_hit, target_price = (False, None)
            if not position["tp1_done"]:
                target_hit, target_price = _bar_hit(bar, direction, position["target1"], False)
            # Conservative intrabar ordering: stop before any target.
            if stop_hit:
                reason = "STOP_LOSS_AFTER_TP1" if position["tp1_done"] else "STOP_LOSS"
                equity = _close_quantity(position, stop_price, position["remaining_quantity"], reason, market, equity)
                position["last_exit_time"] = pd.Timestamp(bar["close_time"]).isoformat()
                _finalize(position, trades)
                position = None
            elif target_hit:
                qty = min(position["initial_quantity"] * 0.30, position["remaining_quantity"])
                equity = _close_quantity(position, target_price, qty, "TAKE_PROFIT_1", market, equity)
                position["tp1_done"] = True
                buffer = position["round_trip_cost"]
                position["stop"] = (position["entry_fill"] * (1 + buffer) if direction == "LONG"
                                    else position["entry_fill"] * (1 - buffer))
                position["best_price"] = float(bar["high"] if direction == "LONG" else bar["low"])
                position["last_exit_time"] = pd.Timestamp(bar["close_time"]).isoformat()

        # After TP1, trail the remaining position using only candles closed
        # through the current 5m bar. The updated stop is active from the next bar.
        if position is not None and position["tp1_done"]:
            trail_frame = base.iloc[max(0, i - 60):i + 1]
            trail = calculate_trailing_stop(
                trail_frame, position["direction"], position["stop"],
                position.get("best_price", position["entry_fill"]),
                float(bar["close"]),
            )
            if trail is not None:
                position["stop"] = float(trail["stop"])
                position["best_price"] = float(trail["best_price"])
                position["trailing_atr"] = float(trail["atr"])

        mark_equity = equity
        if position is not None:
            close = float(bar["close"])
            unrealized = ((close - position["entry_fill"]) * position["remaining_quantity"]
                          if position["direction"] == "LONG"
                          else (position["entry_fill"] - close) * position["remaining_quantity"])
            mark_equity += unrealized
        peak = max(peak, mark_equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - mark_equity) / peak)
        if position is not None or i + 1 >= len(base):
            continue

        agent_data = {"symbol": symbol, "orderbook": {"available": False}}
        ready = True
        for tf in TIMEFRAMES[market]:
            count = int(np.searchsorted(frame_times[tf], asof, side="right"))
            if count < 210:
                ready = False
                break
            agent_data[tf] = prepared[tf].iloc[max(0, count - 220):count].copy()
        if not ready:
            continue

        signal = agent.analyze(agent_data)
        agent.signals.clear()
        raw_direction = str(signal.get("direction", "WAIT")).upper()
        if market == "futures":
            if raw_direction not in ("LONG", "SHORT"):
                continue
            direction = raw_direction
        else:
            if raw_direction != "BUY":
                continue
            direction = "LONG"

        plan = planner.create(agent_data, direction, min_reward_risk=1.5,
                              preferred_timeframe=BASE_TIMEFRAME, market=market)
        if plan.get("success") is not True:
            continue

        next_bar = base.iloc[i + 1]
        raw_entry, planned_entry = float(next_bar["open"]), float(plan["entry"])
        atr = float(plan.get("atr") or 0)
        if atr <= 0 or abs(raw_entry - planned_entry) > max(0.10 * atr, planned_entry * 0.0001):
            continue
        _CURRENT_EXECUTION_COMPONENTS = cost_model.components(next_bar)
        SLIPPAGE_RATE[market] = _CURRENT_EXECUTION_COMPONENTS["total_adverse_rate"]
        entry_fill = _fill_entry(raw_entry, direction, SLIPPAGE_RATE[market])
        stop, target1 = float(plan["stop_loss"]), float(plan["take_profit"])
        target2 = float(plan["take_profit_2"]) if plan.get("take_profit_2") is not None else None
        if (direction == "LONG" and not stop < entry_fill < target1) or (direction == "SHORT" and not target1 < entry_fill < stop):
            continue

        risk_per_unit = abs(entry_fill - stop)
        if risk_per_unit <= 0:
            continue
        qty = min(equity * RISK_FRACTION / risk_per_unit,
                  equity * MAX_NOTIONAL_MULTIPLE / entry_fill)
        if not math.isfinite(qty) or qty <= 0:
            continue
        entry_fee = entry_fill * qty * FEE_RATE[market]
        equity -= entry_fee
        position = {
            "symbol": symbol, "market": market, "direction": direction,
            "timeframe": BASE_TIMEFRAME,
            "entry_time": pd.Timestamp(next_bar["open_time"]).isoformat(),
            "entry_fill": entry_fill, "initial_quantity": qty,
            "entry_time_ms": int(pd.Timestamp(next_bar["open_time"]).timestamp() * 1000),
            "funding_pnl": 0.0, "funding_settlements": 0,
            "spread_cost": raw_entry * qty * _CURRENT_EXECUTION_COMPONENTS["half_spread_rate"],
            "slippage_cost": raw_entry * qty * _CURRENT_EXECUTION_COMPONENTS["slippage_rate"],
            "mae_pct": 0.0, "mfe_pct": 0.0,
            "remaining_quantity": qty, "initial_stop": stop, "stop": stop,
            "initial_target": target1, "target1": target1, "target2": target2,
            "tp1_done": False, "strategy": str(plan.get("entry_strategy") or "unknown"),
            "net_pnl": -entry_fee, "fees": entry_fee,
            "round_trip_cost": 2 * (FEE_RATE[market] + SLIPPAGE_RATE[market]),
            "last_exit_reason": "OPEN",
            "last_exit_time": pd.Timestamp(next_bar["open_time"]).isoformat(),
        }

    if position is not None:
        final_bar = base.iloc[-1]
        equity = _close_quantity(position, float(final_bar["close"]), position["remaining_quantity"], "END_OF_DATA", market, equity)
        position["last_exit_time"] = pd.Timestamp(final_bar["close_time"]).isoformat()
        _finalize(position, trades)
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak)

    start_label = first_time or pd.Timestamp(base["close_time"].iloc[0]).isoformat()
    end_label = pd.Timestamp(base["close_time"].iloc[-1]).isoformat()
    return _metrics(trades, equity, max_drawdown, market, symbol, start_label, end_label), trades



def main():
    parser = argparse.ArgumentParser(description="AI-Trader per-coin historical backtest")
    parser.add_argument("--years", type=int, choices=(1, 2, 3), default=2)
    parser.add_argument("--symbols", nargs="+", default=list(SYMBOLS))
    parser.add_argument("--output", default="backtest_results")
    parser.add_argument("--cache", default="data/backtest_cache")
    args = parser.parse_args()
    invalid = sorted(set(args.symbols).difference(SYMBOLS))
    if invalid:
        parser.error("Unsupported symbols: " + ", ".join(invalid))

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    market_engine, planner = MarketDataEngine(), TradePlanner()
    all_summaries, all_trades = [], []

    # Process one coin at a time, completing both markets before moving on.
    for coin_number, symbol in enumerate(args.symbols, 1):
        coin_dir = output / symbol
        coin_dir.mkdir(parents=True, exist_ok=True)
        coin_summaries, coin_trades = [], []
        print(f"\n========== COIN {coin_number}/{len(args.symbols)}: {symbol} ==========", flush=True)

        for market in ("futures", "spot"):
            print(f"\n===== {symbol} {market.upper()} =====", flush=True)
            metrics, trades = run_one(
                None, market_engine, planner, market, symbol, args.years, Path(args.cache)
            )
            coin_summaries.append(metrics)
            coin_trades.extend(trades)
            all_summaries.append(metrics)
            all_trades.extend(trades)

            # Durable checkpoint after each market.
            (coin_dir / f"{market}_summary.json").write_text(
                json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            pd.DataFrame(trades).to_csv(coin_dir / f"{market}_trades.csv", index=False)
            (coin_dir / "progress.json").write_text(
                json.dumps({
                    "symbol": symbol,
                    "years_requested": args.years,
                    "completed_markets": [x["market"] for x in coin_summaries],
                    "updated_at_utc": datetime.now(timezone.utc).isoformat(),
                }, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"CHECKPOINT SAVED: {symbol} {market.upper()} ({len(trades)} trades)", flush=True)
            print(json.dumps(metrics, ensure_ascii=False, indent=2), flush=True)

        coin_report = {
            "engine": "production_agents_plus_production_trade_planner",
            "symbol": symbol,
            "years_requested": args.years,
            "markets": coin_summaries,
            "trades": len(coin_trades),
            "net_pnl_combined": round(sum(float(x["net_pnl"]) for x in coin_summaries), 4),
            "limitations": [
                "No historical order-book imbalance.",
                "Futures funding costs are not included.",
                "Taker fees and fixed slippage are modeled on both sides.",
                "1x notional sizing is used; leverage effects are excluded.",
                "No look-ahead: indicators are causal, decisions use closed candles, entries use next-bar open.",
            ],
        }
        (coin_dir / "report.json").write_text(
            json.dumps(coin_report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        pd.DataFrame(coin_trades).to_csv(coin_dir / "trades.csv", index=False)
        print(f"COIN REPORT COMPLETE: {symbol}", flush=True)

    report = {
        "engine": "production_agents_plus_production_trade_planner",
        "years_requested": args.years,
        "symbols": args.symbols,
        "results": all_summaries,
        "completed_coins": args.symbols,
    }
    (output / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    pd.DataFrame(all_trades).to_csv(output / "trades.csv", index=False)
    print(f"\nALL COINS COMPLETE: {output / 'summary.json'}", flush=True)


if __name__ == "__main__":
    main()
