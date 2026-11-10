import sqlite3
from decimal import Decimal, InvalidOperation
import threading
from contextlib import contextmanager
from pathlib import Path


class _DecimalSum:
    def __init__(self):
        self.values = []
        self.valid = True

    def step(self, value):
        try:
            number = Decimal(str(value))
            if not number.is_finite():
                self.valid = False
                return
            self.values.append(number)
        except (InvalidOperation, TypeError, ValueError):
            self.valid = False

    def finalize(self):
        if not self.valid:
            return None
        if not self.values:
            return "0"

        parts = [value.as_tuple() for value in self.values]
        min_exp = min(part.exponent for part in parts)
        total = 0

        for sign, digits, exponent in parts:
            coefficient = int("".join(map(str, digits)) or "0")
            if sign:
                coefficient = -coefficient
            total += coefficient * (10 ** (exponent - min_exp))

        if total == 0:
            return "0"

        sign = int(total < 0)
        digits = tuple(int(ch) for ch in str(abs(total)))
        return str(Decimal((sign, digits, min_exp)))


def _decimal_line_valid(debit, credit):
    try:
        d = Decimal(str(debit))
        c = Decimal(str(credit))
        if not d.is_finite() or not c.is_finite():
            return 0
        if d < 0 or c < 0:
            return 0
        return int((d > 0) != (c > 0))
    except (InvalidOperation, TypeError, ValueError):
        return 0


def _decimal_equal(left, right):
    try:
        a = Decimal(str(left))
        b = Decimal(str(right))
        return int(a.is_finite() and b.is_finite() and a == b)
    except (InvalidOperation, TypeError, ValueError):
        return 0


class _BufferedCursor:
    """Materialized cursor result; no SQLite cursor escapes the connection lock."""

    def __init__(self, cursor, rows):
        self.description = cursor.description
        self.rowcount = cursor.rowcount
        self.lastrowid = cursor.lastrowid
        self._rows = list(rows)
        self._index = 0

    def fetchone(self):
        if self._index >= len(self._rows):
            return None
        row = self._rows[self._index]
        self._index += 1
        return row

    def fetchall(self):
        rows = self._rows[self._index:]
        self._index = len(self._rows)
        return rows

    def fetchmany(self, size=1):
        end = min(len(self._rows), self._index + max(0, int(size)))
        rows = self._rows[self._index:end]
        self._index = end
        return rows

    def __iter__(self):
        return self

    def __next__(self):
        row = self.fetchone()
        if row is None:
            raise StopIteration
        return row


class _LockedConnection:
    """Serialize every operation on the shared SQLite connection.

    Reads are fully materialized while holding the same re-entrant lock used
    by transactions. This prevents request/monitor threads from interleaving
    statements on one check_same_thread=False connection.
    """

    def __init__(self, connection, lock):
        self._connection = connection
        self._lock = lock

    def execute(self, sql, parameters=()):
        with self._lock:
            cursor = self._connection.execute(sql, parameters)
            rows = cursor.fetchall() if cursor.description is not None else ()
            return _BufferedCursor(cursor, rows)

    def executemany(self, sql, seq_of_parameters):
        with self._lock:
            cursor = self._connection.executemany(sql, seq_of_parameters)
            rows = cursor.fetchall() if cursor.description is not None else ()
            return _BufferedCursor(cursor, rows)

    def executescript(self, sql_script):
        with self._lock:
            cursor = self._connection.executescript(sql_script)
            rows = cursor.fetchall() if cursor.description is not None else ()
            return _BufferedCursor(cursor, rows)

    def commit(self):
        with self._lock:
            return self._connection.commit()

    def rollback(self):
        with self._lock:
            return self._connection.rollback()

    def close(self):
        with self._lock:
            return self._connection.close()

    def __getattr__(self, name):
        return getattr(self._connection, name)


class DemoDatabase:
    """Owns one SQLite connection shared by DEMO components."""

    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.RLock()
        raw_connection = sqlite3.connect(
            str(self.db_path),
            timeout=30,
            check_same_thread=False,
        )
        raw_connection.row_factory = sqlite3.Row
        self.connection = _LockedConnection(raw_connection, self._lock)
        self.connection.create_function(
            "demo_decimal_line_valid", 2,
            _decimal_line_valid,
        )
        self.connection.create_function(
            "demo_decimal_equal", 2, _decimal_equal,
        )
        self.connection.create_aggregate(
            "demo_decimal_sum", 1, _DecimalSum,
        )
        with self._lock:
            self.connection.execute("PRAGMA busy_timeout = 30000")
            self.connection.execute("PRAGMA foreign_keys = ON")
            self.connection.execute("PRAGMA journal_mode = WAL")
        self._depth = 0
        self._savepoint_id = 0
        self._closed = False

    @contextmanager
    def transaction(self):
        with self._lock:
            if self._closed:
                raise RuntimeError("Database is closed")

            depth = self._depth
            savepoint = None

            if depth == 0:
                self.connection.execute("BEGIN IMMEDIATE")
            else:
                self._savepoint_id += 1
                savepoint = f"demo_sp_{self._savepoint_id}"
                self.connection.execute(
                    f"SAVEPOINT {savepoint}"
                )

            self._depth += 1

            try:
                yield self.connection
            except BaseException:
                self._depth -= 1

                if depth == 0:
                    self.connection.rollback()
                else:
                    self.connection.execute(
                        f"ROLLBACK TO SAVEPOINT {savepoint}"
                    )
                    self.connection.execute(
                        f"RELEASE SAVEPOINT {savepoint}"
                    )
                raise
            else:
                self._depth -= 1

                if depth == 0:
                    self.connection.commit()
                else:
                    self.connection.execute(
                        f"RELEASE SAVEPOINT {savepoint}"
                    )

    def close(self):
        with self._lock:
            if not self._closed:
                if self._depth:
                    raise RuntimeError(
                        "Cannot close database during a transaction"
                    )
                self.connection.close()
                self._closed = True
