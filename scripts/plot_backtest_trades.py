"""Render one evidence-based OHLC chart for every completed historical trade."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Rectangle


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(value)).strip("_")


def _nearest_index(series: pd.Series, value: pd.Timestamp) -> int:
    delta = (series - value).abs()
    return int(delta.to_numpy().argmin())


def render_trade(trade: pd.Series, candles: pd.DataFrame, number: int, output: Path) -> str:
    candles = candles.copy()
    candles["open_time"] = pd.to_datetime(candles["open_time"], utc=True)
    candles["close_time"] = pd.to_datetime(candles["close_time"], utc=True)
    for column in ("open", "high", "low", "close", "volume"):
        candles[column] = pd.to_numeric(candles[column], errors="coerce")
    candles = candles.dropna(subset=["open_time", "open", "high", "low", "close"]).reset_index(drop=True)

    entry_time = pd.to_datetime(trade["entry_time"], utc=True)
    exit_time = pd.to_datetime(trade["exit_time"], utc=True)
    entry_idx = _nearest_index(candles["open_time"], entry_time)
    exit_idx = _nearest_index(candles["close_time"], exit_time)
    if exit_idx < entry_idx:
        exit_idx = entry_idx

    left = max(0, entry_idx - 30)
    right = min(len(candles), exit_idx + 21)
    view = candles.iloc[left:right].reset_index(drop=True)
    if view.empty:
        raise ValueError(f"No candle window for trade {number}")

    entry_x = entry_idx - left
    exit_x = exit_idx - left
    x = range(len(view))
    fig, ax = plt.subplots(figsize=(17, 9), dpi=130)
    fig.patch.set_facecolor("#101827")
    ax.set_facecolor("#101827")
    for spine in ax.spines.values():
        spine.set_color("#344256")
    ax.tick_params(colors="#cbd5e1", labelsize=8)
    ax.grid(True, color="#334155", alpha=0.42, linewidth=0.6)

    for i, row in enumerate(view.itertuples(index=False)):
        rising = float(row.close) >= float(row.open)
        candle_color = "#22c55e" if rising else "#ef4444"
        ax.vlines(i, float(row.low), float(row.high), color=candle_color, linewidth=1.0, zorder=2)
        body_low = min(float(row.open), float(row.close))
        body_height = max(abs(float(row.close) - float(row.open)), max(abs(float(row.close)), 1.0) * 0.000015)
        ax.add_patch(Rectangle((i - 0.32, body_low), 0.64, body_height,
                               facecolor=candle_color, edgecolor=candle_color, linewidth=0.7, zorder=3))

    entry = float(trade["entry_price"])
    stop = float(trade["stop_loss"])
    target = float(trade["take_profit"])
    exit_price = float(trade["last_exit_price"])
    ax.axhline(entry, color="#38bdf8", linewidth=1.25, linestyle="-", label=f"Entry {entry:.8g}")
    ax.axhline(stop, color="#fb7185", linewidth=1.35, linestyle="--", label=f"Initial SL {stop:.8g}")
    ax.axhline(target, color="#4ade80", linewidth=1.35, linestyle="--", label=f"TP1 {target:.8g}")
    ax.axhline(exit_price, color="#fbbf24", linewidth=1.1, linestyle=":", label=f"Actual final exit {exit_price:.8g}")
    ax.axvline(entry_x, color="#38bdf8", alpha=0.75, linewidth=1.0)
    ax.axvline(exit_x, color="#fbbf24", alpha=0.8, linewidth=1.0)
    ax.scatter([entry_x], [entry], marker="^" if str(trade["direction"]).upper() == "LONG" else "v",
               s=150, color="#38bdf8", edgecolors="#e0f2fe", linewidths=0.8, zorder=6, label="Entry fill")
    ax.scatter([exit_x], [exit_price], marker="X", s=150, color="#fbbf24",
               edgecolors="#fff7ed", linewidths=0.8, zorder=7, label="Actual exit")

    labels = [view["open_time"].iloc[i].strftime("%Y-%m-%d %H:%M") for i in range(0, len(view), max(1, len(view)//7))]
    positions = list(range(0, len(view), max(1, len(view)//7)))
    ax.set_xticks(positions, labels, rotation=18, ha="right")
    pnl = float(trade["net_pnl"])
    fees = float(trade["fees"])
    market = str(trade["market"]).upper()
    symbol = str(trade["symbol"])
    direction = str(trade["direction"]).upper()
    reason = str(trade["exit_reason"])
    strategy = str(trade.get("strategy", "unknown"))
    ax.set_title(
        f"TRADE #{number:02d}  |  {symbol} {market} {direction}  |  {trade['timeframe']}\n"
        f"Strategy: {strategy}  |  Net PnL: {pnl:+.4f} USDT  |  Fees: {fees:.4f} USDT  |  Exit: {reason}",
        color="#f8fafc", fontsize=13, fontweight="bold", pad=16,
    )
    ax.set_ylabel("Price (USDT)", color="#cbd5e1")
    ax.set_xlabel("UTC time — actual Binance Vision 5m candles", color="#cbd5e1")
    legend = ax.legend(loc="best", fontsize=8, facecolor="#1e293b", edgecolor="#475569", labelcolor="#f8fafc")
    for text_item in legend.get_texts():
        text_item.set_color("#f8fafc")
    ax.text(0.01, 0.015, f"Entry: {entry_time:%Y-%m-%d %H:%M UTC}\nExit: {exit_time:%Y-%m-%d %H:%M UTC}",
            transform=ax.transAxes, color="#cbd5e1", fontsize=8, va="bottom",
            bbox={"facecolor": "#1e293b", "edgecolor": "#475569", "alpha": 0.9, "pad": 5})

    filename = f"trade_{number:03d}_{_safe(symbol)}_{_safe(market)}_{_safe(direction)}.png"
    fig.tight_layout()
    fig.savefig(output / filename, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return filename


def main() -> None:
    parser = argparse.ArgumentParser(description="Create one OHLC chart per completed backtest trade")
    parser.add_argument("--trades", default="backtest_results/trades.csv")
    parser.add_argument("--cache", default="data/backtest_cache")
    parser.add_argument("--output", default="backtest_results/trade_charts")
    parser.add_argument("--years", type=int, default=1)
    args = parser.parse_args()

    trades_path = Path(args.trades)
    cache = Path(args.cache)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    trades = pd.read_csv(trades_path)
    if trades.empty:
        print("Backtest produced zero trades; no trade charts are applicable.", flush=True)
        return

    chart_files = []
    candle_cache: dict[tuple[str, str], pd.DataFrame] = {}
    for index, trade in trades.iterrows():
        key = (str(trade["market"]), str(trade["symbol"]))
        if key not in candle_cache:
            candle_path = cache / f"{key[0]}_{key[1]}_5m_{args.years}y.csv"
            if not candle_path.exists():
                raise FileNotFoundError(f"Missing actual 5m OHLC cache: {candle_path}")
            candle_cache[key] = pd.read_csv(candle_path)
        filename = render_trade(trade, candle_cache[key], index + 1, output)
        chart_files.append(filename)
        print(f"Rendered trade {index + 1}/{len(trades)}: {filename}", flush=True)

    trades["chart_file"] = [f"trade_charts/{name}" for name in chart_files]
    trades.to_csv(trades_path, index=False)
    print(f"Created {len(chart_files)} trade charts in {output}", flush=True)


if __name__ == "__main__":
    main()
