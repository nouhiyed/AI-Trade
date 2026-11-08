"""Trade journal: every DEMO trade with the signal context it was opened under.

This is the data the Learning Engine and the performance screen are built on.
SQLite, one short-lived connection per call (safe across threads, no leaks).
"""
import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    trade_id    TEXT PRIMARY KEY,
    domain      TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    direction   TEXT NOT NULL,
    setup_key   TEXT NOT NULL,
    confidence  REAL,
    opened_at   INTEGER NOT NULL,
    closed_at   INTEGER,
    entry       REAL,
    stop_loss   REAL,
    take_profit REAL,
    risk_amount REAL,
    exit_price  REAL,
    close_reason TEXT,
    net_pnl     REAL,
    r_multiple  REAL,
    context     TEXT,
    status      TEXT NOT NULL DEFAULT 'OPEN'
);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_setup ON trades(setup_key);
CREATE TABLE IF NOT EXISTS setup_state (
    setup_key TEXT PRIMARY KEY,
    disabled  INTEGER NOT NULL DEFAULT 0,
    reason    TEXT,
    updated_at INTEGER NOT NULL
);
"""


class TradeJournal:

    def __init__(self, path="data/journal.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connect() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(str(self.path), timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    # ---- writes ----------------------------------------------------------

    def record_open(self, trade_id, domain, symbol, direction, setup_key,
                    confidence, entry, stop_loss, take_profit,
                    risk_amount=None, context=None):
        with self._lock, self._connect() as db:
            db.execute(
                """INSERT OR REPLACE INTO trades
                   (trade_id, domain, symbol, direction, setup_key, confidence,
                    opened_at, entry, stop_loss, take_profit, risk_amount,
                    context, status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'OPEN')""",
                (str(trade_id), domain, symbol, direction, setup_key,
                 _num(confidence), int(time.time() * 1000), _num(entry),
                 _num(stop_loss), _num(take_profit), _num(risk_amount),
                 json.dumps(context or {}, default=str)),
            )

    def record_close(self, trade_id, net_pnl, exit_price=None, reason=None):
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT risk_amount FROM trades WHERE trade_id=?",
                (str(trade_id),)).fetchone()
            if row is None:
                return False
            risk = row["risk_amount"]
            r_mult = (net_pnl / risk) if risk else None
            db.execute(
                """UPDATE trades SET closed_at=?, exit_price=?, close_reason=?,
                   net_pnl=?, r_multiple=?, status='CLOSED' WHERE trade_id=?""",
                (int(time.time() * 1000), _num(exit_price), reason,
                 float(net_pnl), r_mult, str(trade_id)),
            )
            return True

    def set_setup_disabled(self, setup_key, disabled, reason=""):
        with self._lock, self._connect() as db:
            db.execute(
                """INSERT INTO setup_state (setup_key, disabled, reason, updated_at)
                   VALUES (?,?,?,?)
                   ON CONFLICT(setup_key) DO UPDATE SET disabled=excluded.disabled,
                   reason=excluded.reason, updated_at=excluded.updated_at""",
                (setup_key, 1 if disabled else 0, reason,
                 int(time.time() * 1000)),
            )

    # ---- reads -----------------------------------------------------------

    def closed_trades(self, limit=None):
        sql = "SELECT * FROM trades WHERE status='CLOSED' ORDER BY closed_at"
        with self._connect() as db:
            rows = [dict(r) for r in db.execute(sql).fetchall()]
        return rows[-limit:] if limit else rows

    def recent(self, limit=50):
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM trades ORDER BY opened_at DESC LIMIT ?",
                (int(limit),)).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            try:
                item["context"] = json.loads(item.get("context") or "{}")
            except ValueError:
                item["context"] = {}
            out.append(item)
        return out

    def disabled_setups(self):
        with self._connect() as db:
            return {r["setup_key"]: r["reason"] for r in db.execute(
                "SELECT setup_key, reason FROM setup_state WHERE disabled=1")}


def _num(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None
