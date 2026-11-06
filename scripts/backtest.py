
import json
import time
from pathlib import Path

import pandas as pd

from core.technical import analyze
from core.market_structure import analyze_market_structure
from agents.futures.agent import FuturesAgent
from agents.spot.agent import SpotAgent

DATA = Path("data/history")
OUT = Path("data/backtest")
OUT.mkdir(parents=True, exist_ok=True)

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

# إعدادات المحاكاة
START_BALANCE = 1000.0
TRADE_NOTIONAL = 100.0
FEE_RATE = 0.001
ATR_MULTIPLIER = 1.5
REWARD_RISK = 2.0

CONFIG = {
    "futures": {
        "agent": FuturesAgent,
        "timeframes": ["1m", "5m", "15m", "1h"],
        "decision_tf": "15m",
        "directions": ["LONG", "SHORT"],
    },
    "spot": {
        "agent": SpotAgent,
        "timeframes": ["5m", "15m", "1h", "4h"],
        "decision_tf": "1h",
        "directions": ["BUY"],
    },
}


def load_data(symbol, interval):
    path = DATA / f"{symbol}_{interval}.csv"

    if not path.exists():
        raise FileNotFoundError(str(path))

    df = pd.read_csv(path)

    required = [
        "open_time", "close_time",
        "open", "high", "low", "close", "volume"
    ]

    if any(c not in df.columns for c in required):
        raise ValueError(f"Invalid columns: {path}")

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["open_time"] = pd.to_numeric(
        df["open_time"], errors="coerce"
    )
    df["close_time"] = pd.to_numeric(
        df["close_time"], errors="coerce"
    )

    df = df.dropna(subset=required)
    df = df.sort_values("open_time")
    df = df.drop_duplicates("open_time")
    df = df.reset_index(drop=True)

    df["time"] = pd.to_datetime(
        df["close_time"], unit="ms", utc=True
    )

    # حساب المؤشرات والبنية مرة واحدة على كامل السلسلة.
    df = analyze(df)
    df = analyze_market_structure(df)

    df = df.replace([float("inf"), float("-inf")], pd.NA)

    return df


def prepare_symbol(symbol, timeframes):
    result = {}

    for tf in timeframes:
        print(f"Loading {symbol} {tf}...", flush=True)
        result[tf] = load_data(symbol, tf)

    return result


def get_history(data, timestamp, limit=300):
    times = data["time"].astype("int64").to_numpy()
    target = timestamp.value

    end = times.searchsorted(target, side="right")

    if end < 210:
        return None

    return data.iloc[max(0, end - limit):end].copy()


def get_market_data(frames, timestamp, symbol):
    result = {"symbol": symbol}

    for tf, df in frames.items():
        history = get_history(df, timestamp)

        if history is None:
            return None

        result[tf] = history

    # لا نستخدم Order Book الحالي في اختبار تاريخي.
    result["orderbook"] = {"available": False}

    return result


def calculate_equity(trades):
    equity = START_BALANCE
    peak = equity
    max_drawdown = 0.0

    for trade in trades:
        equity += trade["pnl"]
        peak = max(peak, equity)

        if peak > 0:
            drawdown = (peak - equity) / peak * 100
            max_drawdown = max(max_drawdown, drawdown)

    return equity, max_drawdown


def run_backtest(symbol, domain, frames):
    cfg = CONFIG[domain]
    agent = cfg["agent"]()

    decision_tf = cfg["decision_tf"]
    execution = frames[decision_tf]

    trades = []
    active = None

    warmup = 220
    total = len(execution)

    print(
        f"\nBacktesting {symbol} / {domain} "
        f"| candles={total}",
        flush=True
    )

    for i in range(warmup, total - 1):
        current = execution.iloc[i]
        next_bar = execution.iloc[i + 1]

        timestamp = current["time"]

        # فحص وقف الخسارة والهدف أولاً.
        if active is not None:
            high = float(current["high"])
            low = float(current["low"])

            exit_price = None
            exit_reason = None

            if active["direction"] == "LONG":
                stop_hit = low <= active["stop"]
                target_hit = high >= active["target"]

                if stop_hit:
                    exit_price = active["stop"]
                    exit_reason = "STOP"
                elif target_hit:
                    exit_price = active["target"]
                    exit_reason = "TARGET"

            else:
                stop_hit = high >= active["stop"]
                target_hit = low <= active["target"]

                if stop_hit:
                    exit_price = active["stop"]
                    exit_reason = "STOP"
                elif target_hit:
                    exit_price = active["target"]
                    exit_reason = "TARGET"

            if exit_price is not None:
                qty = active["quantity"]

                if active["direction"] == "LONG":
                    gross = (exit_price - active["entry"]) * qty
                else:
                    gross = (active["entry"] - exit_price) * qty

                fees = (
                    active["entry"] * qty * FEE_RATE
                    + exit_price * qty * FEE_RATE
                )

                pnl = gross - fees

                trades.append({
                    "symbol": symbol,
                    "domain": domain,
                    "direction": active["direction"],
                    "entry_time": str(active["entry_time"]),
                    "exit_time": str(timestamp),
                    "entry": active["entry"],
                    "exit": exit_price,
                    "stop": active["stop"],
                    "target": active["target"],
                    "quantity": qty,
                    "gross_pnl": gross,
                    "fees": fees,
                    "pnl": pnl,
                    "result": exit_reason,
                })

                active = None

        if active is not None:
            continue

        # تجهيز بيانات الوكيل حتى لحظة القرار فقط.
        market = get_market_data(
            frames, timestamp, symbol
        )

        if market is None:
            continue

        signal = agent.analyze(market)

        direction = signal.get("direction")
        confidence = float(signal.get("confidence", 0))

        if direction not in cfg["directions"]:
            continue

        if confidence < 25:
            continue

        last = market[decision_tf].iloc[-1]

        atr = last.get("ATR")

        if pd.isna(atr):
            continue

        atr = float(atr)

        if atr <= 0:
            continue

        # التنفيذ على افتتاح الشمعة التالية للإشارة.
        entry = float(next_bar["open"])

        if entry <= 0:
            continue

        risk_distance = atr * ATR_MULTIPLIER

        if direction in ("LONG", "BUY"):
            direction = "LONG"
            stop = entry - risk_distance
            target = entry + risk_distance * REWARD_RISK
        else:
            stop = entry + risk_distance
            target = entry - risk_distance * REWARD_RISK

        if stop <= 0 or target <= 0:
            continue

        quantity = TRADE_NOTIONAL / entry

        active = {
            "direction": direction,
            "entry": entry,
            "stop": stop,
            "target": target,
            "quantity": quantity,
            "entry_time": next_bar["time"],
        }

    # إغلاق أي صفقة متبقية عند آخر سعر متاح.
    if active is not None:
        last = execution.iloc[-1]
        exit_price = float(last["close"])

        qty = active["quantity"]

        if active["direction"] == "LONG":
            gross = (exit_price - active["entry"]) * qty
        else:
            gross = (active["entry"] - exit_price) * qty

        fees = (
            active["entry"] * qty * FEE_RATE
            + exit_price * qty * FEE_RATE
        )

        trades.append({
            "symbol": symbol,
            "domain": domain,
            "direction": active["direction"],
            "entry_time": str(active["entry_time"]),
            "exit_time": str(last["time"]),
            "entry": active["entry"],
            "exit": exit_price,
            "stop": active["stop"],
            "target": active["target"],
            "quantity": qty,
            "gross_pnl": gross,
            "fees": fees,
            "pnl": gross - fees,
            "result": "END_OF_DATA",
        })

    return trades


def summarize(trades):
    if not trades:
        return {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0,
            "net_pnl": 0,
            "fees": 0,
            "ending_balance": START_BALANCE,
            "max_drawdown_pct": 0,
        }

    wins = sum(t["pnl"] > 0 for t in trades)
    losses = sum(t["pnl"] <= 0 for t in trades)

    net = sum(t["pnl"] for t in trades)
    fees = sum(t["fees"] for t in trades)

    balance, drawdown = calculate_equity(trades)

    return {
        "trades": len(trades),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / len(trades) * 100, 2),
        "net_pnl": round(net, 4),
        "fees": round(fees, 4),
        "ending_balance": round(balance, 4),
        "max_drawdown_pct": round(drawdown, 2),
    }


def main():
    all_trades = []
    reports = {}

    for symbol in SYMBOLS:
        for domain, cfg in CONFIG.items():
            try:
                frames = prepare_symbol(
                    symbol, cfg["timeframes"]
                )

                trades = run_backtest(
                    symbol, domain, frames
                )

                all_trades.extend(trades)

                key = f"{symbol}_{domain}"
                reports[key] = summarize(trades)

                print(
                    key,
                    json.dumps(
                        reports[key],
                        ensure_ascii=False
                    ),
                    flush=True
                )

            except Exception as exc:
                reports[f"{symbol}_{domain}"] = {
                    "error": str(exc)
                }

                print(
                    "ERROR",
                    symbol,
                    domain,
                    repr(exc),
                    flush=True
                )

    # نتائج Alpha لا يمكن اختبارها تاريخياً
    # دون بيانات أسعار خاصة بالتوكنات وفحص أمان تاريخي.
    reports["alpha"] = {
        "status": "NOT_TESTED",
        "reason": (
            "Token-specific historical prices and "
            "historical safety data are unavailable"
        )
    }

    trades_path = OUT / "trades.csv"
    summary_path = OUT / "summary.json"

    pd.DataFrame(all_trades).to_csv(
        trades_path, index=False
    )

    with open(summary_path, "w") as f:
        json.dump(
            reports,
            f,
            indent=2,
            ensure_ascii=False
        )

    print("\n========== FINAL REPORT ==========")

    for name, report in reports.items():
        print(name, report)

    print("\nSaved:", trades_path)
    print("Saved:", summary_path)
    print("\nBACKTEST FINISHED", flush=True)


if __name__ == "__main__":
    main()

