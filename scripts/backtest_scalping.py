"""Independent 1m execution / 5m signal backtest for separate Spot and Futures scalpers."""
from __future__ import annotations
import argparse, json, sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import pandas as pd
import backtest as engine
from backtest import (SYMBOLS, STARTING_CAPITAL, MAX_NOTIONAL_MULTIPLE, FEE_RATE,
    SLIPPAGE_RATE, download_history, _times_ms, _fill_entry, _bar_hit,
    _close_quantity, _finalize, _metrics)
from core.market_data_engine import MarketDataEngine
from core.backtest_costs import BacktestCostModel, load_funding_history, apply_funding
from core.scalping_strategies import FuturesScalpingStrategy, SpotScalpingStrategy
from core.scalping_v2 import FuturesScalpingStrategyV2, SpotScalpingStrategyV2

RISK_FRACTION = 0.0025
MAX_GAP_ATR = 0.40


def run_one(market, symbol, years, cache_dir, strategy_version='v1'):
    now = datetime.now(timezone.utc)
    end_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_index = end_dt.year * 12 + end_dt.month - 1 - years * 12
    start_dt = datetime(month_index // 12, month_index % 12 + 1, 1, tzinfo=timezone.utc)
    tfs = ("1m", "5m", "15m", "1h", "4h") if market == "spot" else ("1m", "5m", "15m", "1h")
    market_engine, prepared = MarketDataEngine(), {}
    for tf in tfs:
        raw = download_history(market, symbol, tf, start_dt, end_dt, cache_dir, years)
        if tf == "1m":
            # Execution bars need OHLCV, timestamps and a lightweight ATR only.
            # Avoid running the full multi-indicator/SMC pipeline over ~1M rows.
            prev_close = raw["close"].shift(1)
            true_range = pd.concat([
                raw["high"] - raw["low"],
                (raw["high"] - prev_close).abs(),
                (raw["low"] - prev_close).abs(),
            ], axis=1).max(axis=1)
            raw["ATR"] = true_range.rolling(14, min_periods=14).mean()
            prepared[tf] = raw
        else:
            prepared[tf] = market_engine._prepare_frame(raw, symbol, market, tf)
        print(f"Prepared {market} {symbol} {tf}: {len(raw)} candles", flush=True)
    base = prepared["1m"]
    if strategy_version == "v2":
        strategy = FuturesScalpingStrategyV2() if market == "futures" else SpotScalpingStrategyV2()
    else:
        strategy = FuturesScalpingStrategy() if market == "futures" else SpotScalpingStrategy()
    costs = BacktestCostModel(market)
    funding = (load_funding_history(symbol, int(start_dt.timestamp()*1000),
        int(end_dt.timestamp()*1000), cache_dir.parent/"funding_cache") if market == "futures" else [])
    funding_times = [int(x["funding_time"]) for x in funding]
    funding_cursor = 0
    times = {tf: _times_ms(frame) for tf, frame in prepared.items()}
    trades, position = [], None
    equity = peak = STARTING_CAPITAL
    max_dd, first_time, last_signal = 0.0, None, None
    diagnostics, setup_counts = Counter(), Counter()
    for i in range(210, len(base)-1):
        bar, asof = base.iloc[i], int(times["1m"][i])
        engine._CURRENT_EXECUTION_COMPONENTS = costs.components(bar)
        SLIPPAGE_RATE[market] = engine._CURRENT_EXECUTION_COMPONENTS["total_adverse_rate"]
        if first_time is None:
            first_time = pd.Timestamp(bar["close_time"]).isoformat()
        if position is not None:
            while funding_cursor < len(funding) and funding_times[funding_cursor] <= asof:
                event = funding[funding_cursor]
                if funding_times[funding_cursor] > position["entry_time_ms"]:
                    cash = apply_funding(position, event["funding_rate"], float(bar["close"]))
                    position["funding_pnl"] += cash
                    position["funding_settlements"] += 1
                    position["net_pnl"] += cash
                    equity += cash
                funding_cursor += 1
            direction, entry = position["direction"], float(position["entry_fill"])
            high, low, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
            favorable = (high-entry)/entry if direction == "LONG" else (entry-low)/entry
            adverse = (entry-low)/entry if direction == "LONG" else (high-entry)/entry
            position["mfe_pct"] = max(position["mfe_pct"], favorable)
            position["mae_pct"] = max(position["mae_pct"], adverse)
            stop_hit, stop_px = _bar_hit(bar, direction, position["stop"], True)
            target_hit, target_px = _bar_hit(bar, direction, position["target1"], False)
            if stop_hit:
                equity = _close_quantity(position, stop_px, position["remaining_quantity"], "STOP_LOSS", market, equity)
            elif target_hit:
                equity = _close_quantity(position, target_px, position["remaining_quantity"], "TAKE_PROFIT", market, equity)
            else:
                if not position["be_activated"] and favorable >= .9*position["risk_pct"]:
                    pad = .5*position["round_trip_cost"]
                    position["stop"] = entry*(1+pad if direction == "LONG" else 1-pad)
                    position["be_activated"] = True
                if i-position["entry_index"] >= strategy.MAX_HOLD_MINUTES:
                    equity = _close_quantity(position, close, position["remaining_quantity"], "TIME_EXIT", market, equity)
            if stop_hit or target_hit or (position is not None and i-position["entry_index"] >= strategy.MAX_HOLD_MINUTES):
                position["last_exit_time"] = pd.Timestamp(bar["close_time"]).isoformat()
                _finalize(position, trades)
                position = None
        mark_equity = equity
        if position is not None:
            close = float(bar["close"])
            mark_equity += ((close-position["entry_fill"])*position["remaining_quantity"] if position["direction"]=="LONG"
                            else (position["entry_fill"]-close)*position["remaining_quantity"])
        peak = max(peak, mark_equity)
        if peak > 0:
            max_dd = max(max_dd, (peak-mark_equity)/peak)
        if position is not None:
            continue
        n5 = int(times["5m"].searchsorted(asof, side="right"))
        if n5 < 30:
            continue
        signal_time = int(times["5m"][n5-1])
        if signal_time == last_signal:
            continue
        last_signal = signal_time
        data, ready = {"symbol": symbol}, True
        for tf in tfs[1:]:
            count = int(times[tf].searchsorted(asof, side="right"))
            if count < 30:
                ready = False
                break
            data[tf] = prepared[tf].iloc[max(0,count-240):count].copy()
        if not ready:
            continue
        diagnostics["signal_evaluations"] += 1
        plan = strategy.analyze(data, costs.components(data["5m"].iloc[-1]))
        if not plan.get("success"):
            reason = str(plan.get("reason", "unknown")).lower()
            if "cost" in reason or "reward" in reason:
                diagnostics["rejected_cost"] += 1
            elif "no qualifying" in reason:
                diagnostics["no_setup"] += 1
            else:
                diagnostics["rejected_other"] += 1
            continue
        diagnostics["plans_passed"] += 1
        next_bar = base.iloc[i+1]
        raw_entry, atr = float(next_bar["open"]), float(plan["atr"])
        if abs(raw_entry-float(plan["entry"])) > max(MAX_GAP_ATR*atr, float(plan["entry"])*.0012):
            diagnostics["rejected_gap"] += 1
            continue
        engine._CURRENT_EXECUTION_COMPONENTS = costs.components(next_bar)
        SLIPPAGE_RATE[market] = engine._CURRENT_EXECUTION_COMPONENTS["total_adverse_rate"]
        direction = plan["direction"]
        fill = _fill_entry(raw_entry, direction, SLIPPAGE_RATE[market])

        # Re-anchor every level to the executable fill. The old engine kept
        # stop/target at the prior 5m close, silently changing the planned R.
        distance = max(float(plan.get("stop_atr_multiple", 1.15))*atr, fill*.0008)
        target_r = float(plan.get("reward_risk", 1.0))
        stop = fill-distance if direction == "LONG" else fill+distance
        target = fill+target_r*distance if direction == "LONG" else fill-target_r*distance
        fee_rate = float(FEE_RATE[market])
        adverse_rate = float(engine._CURRENT_EXECUTION_COMPONENTS["total_adverse_rate"])
        round_trip_rate = 2.0*(fee_rate+adverse_rate)
        net_reward_rate = target_r*distance/fill-round_trip_rate
        net_risk_rate = distance/fill+round_trip_rate
        net_rr = net_reward_rate/net_risk_rate if net_risk_rate > 0 else 0.0
        if net_reward_rate < 0.00030 or net_rr < (0.30 if strategy_version == "v2" else 0.15):
            diagnostics["rejected_cost_after_fill"] += 1
            continue
        if (direction=="LONG" and not stop<fill<target) or (direction=="SHORT" and not target<fill<stop):
            diagnostics["rejected_invalid_levels"] += 1
            continue
        distance = abs(fill-stop)
        qty = min(equity*RISK_FRACTION/distance, equity*MAX_NOTIONAL_MULTIPLE/fill)
        if qty <= 0:
            diagnostics["rejected_size"] += 1
            continue
        fee = fill*qty*FEE_RATE[market]
        equity -= fee
        entry_time = pd.Timestamp(next_bar["open_time"])
        diagnostics["entries_opened"] += 1
        setup_counts[plan["setup"]] += 1
        position = {
            "symbol":symbol,"market":market,"direction":direction,"timeframe":"1m execution / 5m signal",
            "entry_time":entry_time.isoformat(),"entry_fill":fill,"initial_quantity":qty,"remaining_quantity":qty,
            "entry_time_ms":int(entry_time.timestamp()*1000),"entry_index":i+1,
            "funding_pnl":0.0,"funding_settlements":0,
            "spread_cost":raw_entry*qty*engine._CURRENT_EXECUTION_COMPONENTS["half_spread_rate"],
            "slippage_cost":raw_entry*qty*engine._CURRENT_EXECUTION_COMPONENTS["slippage_rate"],
            "mae_pct":0.0,"mfe_pct":0.0,"initial_stop":stop,"stop":stop,
            "initial_target":target,"target1":target,"target2":None,"tp1_done":False,
            "best_price":fill,"strategy":plan["strategy"],"setup":plan["setup"],
            "market_regime":plan["market_regime"],"signal_entry_price":float(plan["entry"]),
            "planned_reward_risk":target_r,"actual_reward_risk":target_r,
            "net_reward_risk_after_costs":round(net_rr, 5),
            "net_pnl":-fee,"fees":fee,
            "round_trip_cost":round_trip_rate,
            "risk_pct":distance/fill,"be_activated":False,
            "last_exit_reason":"OPEN","last_exit_time":entry_time.isoformat(),
        }
    if position is not None:
        last = base.iloc[-1]
        engine._CURRENT_EXECUTION_COMPONENTS = costs.components(last)
        SLIPPAGE_RATE[market] = engine._CURRENT_EXECUTION_COMPONENTS["total_adverse_rate"]
        equity = _close_quantity(position,float(last["close"]),position["remaining_quantity"],"END_OF_DATA",market,equity)
        position["last_exit_time"] = pd.Timestamp(last["close_time"]).isoformat()
        _finalize(position,trades)
    engine.BASE_TIMEFRAME = "1m"
    metrics = _metrics(trades,equity,max_dd,market,symbol,
        first_time or pd.Timestamp(base["close_time"].iloc[0]).isoformat(),
        pd.Timestamp(base["close_time"].iloc[-1]).isoformat())
    elapsed_days = max(1.0, (pd.Timestamp(base["close_time"].iloc[-1]) - pd.Timestamp(first_time or base["close_time"].iloc[0])).total_seconds()/86400.0)
    holding = [float(t.get("holding_minutes", 0.0)) for t in trades]
    metrics.update({
        "strategy":("futures_scalper_v2" if market=="futures" else "spot_scalper_v2") if strategy_version=="v2" else ("futures_momentum_range_scalper_v1" if market=="futures" else "spot_long_scalper_v1"),
        "strategy_version":strategy_version,
        "trades_per_30_days":round(len(trades)*30.4375/elapsed_days, 3),
        "average_holding_minutes":round(sum(holding)/len(holding), 2) if holding else 0.0,
        "signal_diagnostics":dict(diagnostics),
        "setup_counts":dict(setup_counts),
        "signal_timeframe":"5m","execution_timeframe":"1m","risk_fraction":RISK_FRACTION,
        "max_holding_minutes":strategy.MAX_HOLD_MINUTES,
        "exit_policy":"Fill-anchored SL/TP; cost-adjusted break-even stop after +0.9R; hard time exit.",
        "limitations":[
            "Research simulation only; no exchange orders are sent.",
            "Closed 5m/15m/1h (and Spot 4h) signals; next 1m open fills.",
            "Funding is historical Binance settlement data with 1m close as mark proxy.",
            "Spread/slippage are OHLCV estimates, not historical quotes or queue fills.",
            "Stop is assumed first if stop and target occur in the same 1m candle.",
            "One position per symbol; independent symbol capital, not a shared portfolio."
        ]})
    return metrics,trades


def main():
    parser=argparse.ArgumentParser(description="Separate Spot/Futures scalping research backtest")
    parser.add_argument("--years",type=int,choices=(1,2,3),default=2)
    parser.add_argument("--symbols",nargs="+",default=list(SYMBOLS))
    parser.add_argument("--output",default="scalping_results")
    parser.add_argument("--cache",default="data/backtest_cache")
    parser.add_argument("--strategy-version",choices=("v1","v2"),default="v2")
    args=parser.parse_args()
    invalid=sorted(set(args.symbols).difference(SYMBOLS))
    if invalid: parser.error("Unsupported symbols: "+", ".join(invalid))
    output,cache=Path(args.output),Path(args.cache)
    output.mkdir(parents=True,exist_ok=True)
    summaries,all_trades=[],[]
    for symbol in args.symbols:
        for market in ("futures","spot"):
            print(f"===== SCALPING {symbol} {market.upper()} =====",flush=True)
            metrics,trades=run_one(market,symbol,args.years,cache,args.strategy_version)
            summaries.append(metrics); all_trades.extend(trades)
            folder=output/symbol; folder.mkdir(parents=True,exist_ok=True)
            (folder/f"{market}_summary.json").write_text(json.dumps(metrics,indent=2),encoding="utf-8")
            pd.DataFrame(trades).to_csv(folder/f"{market}_trades.csv",index=False)
            print(json.dumps(metrics,indent=2),flush=True)
    report={"engine":"separate_futures_and_spot_scalpers","strategy_version":args.strategy_version,"years_requested":args.years,
            "symbols":args.symbols,"results":summaries}
    (output/"summary.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    pd.DataFrame(all_trades).to_csv(output/"trades.csv",index=False)
    print(f"SCALPING BACKTEST COMPLETE: {output/'summary.json'}",flush=True)


if __name__=="__main__":
    main()
