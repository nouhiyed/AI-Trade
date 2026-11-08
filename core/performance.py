"""Performance metrics from closed journal trades (pure functions)."""


def _group(trades, key):
    groups = {}
    for trade in trades:
        groups.setdefault(trade.get(key) or "unknown", []).append(trade)
    return groups


def summarize(trades):
    pnls = [float(t["net_pnl"]) for t in trades if t.get("net_pnl") is not None]
    rs = [float(t["r_multiple"]) for t in trades if t.get("r_multiple") is not None]
    count = len(pnls)
    if not count:
        return {"trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
                "net_pnl": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
                "profit_factor": None, "expectancy": 0.0,
                "expectancy_r": None, "max_drawdown": 0.0}
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_win, gross_loss = sum(wins), -sum(losses)

    peak = equity = max_dd = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    return {
        "trades": count,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / count * 100, 2),
        "net_pnl": round(sum(pnls), 4),
        "avg_win": round(gross_win / len(wins), 4) if wins else 0.0,
        "avg_loss": round(-gross_loss / len(losses), 4) if losses else 0.0,
        "profit_factor": round(gross_win / gross_loss, 3) if gross_loss else None,
        "expectancy": round(sum(pnls) / count, 4),
        "expectancy_r": round(sum(rs) / len(rs), 4) if rs else None,
        "max_drawdown": round(max_dd, 4),
    }


def compute(trades):
    """Overall metrics, split by agent domain, by setup and by close reason."""
    trades = [t for t in trades if t.get("status", "CLOSED") == "CLOSED"]
    curve, equity = [], 0.0
    for trade in trades:
        equity += float(trade.get("net_pnl") or 0.0)
        curve.append(round(equity, 4))
    return {
        "overall": summarize(trades),
        "by_domain": {k: summarize(v) for k, v in _group(trades, "domain").items()},
        "by_setup": {k: summarize(v) for k, v in _group(trades, "setup_key").items()},
        "by_reason": {k: summarize(v) for k, v in _group(trades, "close_reason").items()},
        "equity_curve": curve[-200:],
    }
