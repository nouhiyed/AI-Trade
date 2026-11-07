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


class DemoDatabase:
    """Owns one SQLite connection shared by DEMO components."""

    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.connection = sqlite3.connect(
            str(self.db_path),
            timeout=30,
        )
        self.connection.row_factory = sqlite3.Row
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
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")

        self._lock = threading.RLock()
        self._depth = 0
        self._savepoint_id = 0
        self._closed = False

    @contextmanager
    def transaction(self):
        if self._closed:
            raise RuntimeError("Database is closed")

        with self._lock:
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
