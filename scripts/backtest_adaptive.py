"""Historical backtest for Adaptive Trend v1; research only, no order execution."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from backtest import (
    SYMBOLS, STARTING_CAPITAL, MAX_NOTIONAL_MULTIPLE, FEE_RATE,
    SLIPPAGE_RATE, download_history, _times_ms, _fill_entry, _bar_hit,
    _close_quantity, _finalize, _metrics,
)
from core.adaptive_trend import AdaptiveTrendStrategy
from core.market_data_engine import MarketDataEngine

TIMEFRAMES = ("5m", "15m", "1h")
RISK_FRACTION = 0.0025


def run_one(market, symbol, years, cache_dir):
    now = datetime.now(timezone.utc)
    end_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_index = end_dt.year * 12 + end_dt.month - 1 - years * 12
    start_dt = datetime(month_index // 12, month_index % 12 + 1, 1, tzinfo=timezone.utc)
    engine, strategy, prepared = MarketDataEngine(), AdaptiveTrendStrategy(), {}
    for tf in TIMEFRAMES:
        raw = download_history(market, symbol, tf, start_dt, end_dt, cache_dir, years)
        prepared[tf] = engine._prepare_frame(raw, symbol, market, tf)
        print(f"Prepared {market} {symbol} {tf}: {len(raw)} candles", flush=True)

    base = prepared["5m"]
    base_times = _times_ms(base)
    frame_times = {tf: _times_ms(frame) for tf, frame in prepared.items()}
    trades, position = [], None
    equity = peak = STARTING_CAPITAL
    max_drawdown = 0.0
    first_time = None

    for i in range(210, len(base) - 1):
        bar, asof = base.iloc[i], int(base_times[i])
        if first_time is None:
            first_time = pd.Timestamp(bar["close_time"]).isoformat()

        if position is not None:
            direction = position["direction"]
            stop_hit, stop_price = _bar_hit(bar, direction, position["stop"], True)
            target_hit, target_price = (False, None)
            if not position["tp1_done"]:
                target_hit, target_price = _bar_hit(bar, direction, position["target1"], False)
            if stop_hit:
                reason = "TRAILING_STOP" if position["tp1_done"] else "STOP_LOSS"
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

            if position is not None and position["tp1_done"]:
                atr = float(bar.get("ATR", bar.get("atr", 0)) or 0)
                if atr > 0:
                    best = float(bar["high"] if direction == "LONG" else bar["low"])
                    position["best_price"] = (max(position["best_price"], best) if direction == "LONG"
                                              else min(position["best_price"], best))
                    position["stop"] = strategy.update_trailing_stop(
                        direction, position["stop"], position["best_price"], atr, multiplier=3.0
                    )

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

        if position is not None:
            continue

        market_data = {"symbol": symbol}
        ready = True
        for tf in TIMEFRAMES:
            count = int(pd.Series(frame_times[tf]).searchsorted(asof, side="right"))
            if count < (210 if tf == "1h" else 30):
                ready = False
                break
            market_data[tf] = prepared[tf].iloc[max(0, count - 260):count].copy()
        if not ready:
            continue

        plan = strategy.analyze(market_data, market=market)
        if not plan.get("success"):
            continue
        next_bar = base.iloc[i + 1]
        raw_entry = float(next_bar["open"])
        if abs(raw_entry - float(plan["entry"])) > max(0.5 * float(plan["atr"]), float(plan["entry"]) * 0.001):
            continue
        direction = plan["direction"]
        entry_fill = _fill_entry(raw_entry, direction, SLIPPAGE_RATE[market])
        stop, target = float(plan["stop_loss"]), float(plan["take_profit"])
        if (direction == "LONG" and not stop < entry_fill < target) or (
            direction == "SHORT" and not target < entry_fill < stop
        ):
            continue
        qty = strategy.size_position(equity, entry_fill, stop, RISK_FRACTION, MAX_NOTIONAL_MULTIPLE)
        if qty <= 0:
            continue
        entry_fee = entry_fill * qty * FEE_RATE[market]
        equity -= entry_fee
        position = {
            "symbol": symbol, "market": market, "direction": direction, "timeframe": "5m",
            "entry_time": pd.Timestamp(next_bar["open_time"]).isoformat(),
            "entry_fill": entry_fill, "initial_quantity": qty, "remaining_quantity": qty,
            "initial_stop": stop, "stop": stop, "initial_target": target, "target1": target,
            "target2": None, "tp1_done": False, "best_price": entry_fill,
            "strategy": "adaptive_donchian_breakout_retest_v1",
            "net_pnl": -entry_fee, "fees": entry_fee,
            "round_trip_cost": 2 * (FEE_RATE[market] + SLIPPAGE_RATE[market]),
            "last_exit_reason": "OPEN", "last_exit_time": pd.Timestamp(next_bar["open_time"]).isoformat(),
        }

    if position is not None:
        last = base.iloc[-1]
        equity = _close_quantity(position, float(last["close"]), position["remaining_quantity"],
                                 "END_OF_DATA", market, equity)
        position["last_exit_time"] = pd.Timestamp(last["close_time"]).isoformat()
        _finalize(position, trades)

    metrics = _metrics(
        trades, equity, max_drawdown, market, symbol,
        first_time or pd.Timestamp(base["close_time"].iloc[0]).isoformat(),
        pd.Timestamp(base["close_time"].iloc[-1]).isoformat(),
    )
    metrics["strategy"] = "adaptive_donchian_breakout_retest_v1"
    metrics["risk_fraction"] = RISK_FRACTION
    metrics["exit_policy"] = "30% at 2R; remaining 70% protected by break-even then 3x ATR Chandelier stop"
    metrics["limitations"] = [
        "Research-only simulation; no live or DEMO orders are sent.",
        "Uses closed 1h/15m/5m candles and enters at next 5m open.",
        "Taker fees and fixed per-side slippage are modeled; futures funding is not included.",
        "No historical order book, queue position, latency, or partial fill model.",
        "Stop is assumed hit before target when both occur in one 5m candle.",
        "Each symbol is tested independently with its own starting capital; this is not a shared portfolio.",
    ]
    return metrics, trades


def main():
    parser = argparse.ArgumentParser(description="Adaptive Trend v1 research backtest")
    parser.add_argument("--years", type=int, choices=(1, 2, 3), default=2)
    parser.add_argument("--symbols", nargs="+", default=list(SYMBOLS))
    parser.add_argument("--output", default="adaptive_backtest_results")
    parser.add_argument("--cache", default="data/backtest_cache")
    args = parser.parse_args()
    invalid = sorted(set(args.symbols).difference(SYMBOLS))
    if invalid:
        parser.error("Unsupported symbols: " + ", ".join(invalid))
    output, cache = Path(args.output), Path(args.cache)
    output.mkdir(parents=True, exist_ok=True)
    summaries, all_trades = [], []
    engine_name = "adaptive_donchian_breakout_retest_v1"
    for symbol in args.symbols:
        for market in ("futures", "spot"):
            print(f"===== ADAPTIVE {symbol} {market.upper()} =====", flush=True)
            metrics, trades = run_one(market, symbol, args.years, cache)
            summaries.append(metrics)
            all_trades.extend(trades)
            folder = output / symbol
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{market}_summary.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
            pd.DataFrame(trades).to_csv(folder / f"{market}_trades.csv", index=False)
            print(json.dumps(metrics, indent=2), flush=True)
    report = {"engine": engine_name, "years_requested": args.years, "symbols": args.symbols, "results": summaries}
    (output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    pd.DataFrame(all_trades).to_csv(output / "trades.csv", index=False)
    print(f"ADAPTIVE BACKTEST COMPLETE: {output / 'summary.json'}", flush=True)


if __name__ == "__main__":
    main()
