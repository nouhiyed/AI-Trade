from decimal import Decimal, InvalidOperation
from pathlib import Path
import sqlite3

from core.demo.database import DemoDatabase


class Ledger:
    """Double-entry accounting ledger backed by the DEMO journal."""

    def __init__(self, db_path=None, *, database=None):
        if (db_path is None) == (database is None):
            raise ValueError("Provide exactly one of db_path or database")

        self._owns_database = database is None
        self.database = (
            DemoDatabase(Path(db_path)) if self._owns_database else database
        )

        if not isinstance(self.database, DemoDatabase):
            raise TypeError("database must be a DemoDatabase")

        self.connection = self.database.connection
        self._initialize()

    def _initialize(self):
        schema = Path(__file__).with_name("schema.sql")
        # executescript performs implicit transaction boundaries; serialize it
        # with every DemoDatabase transaction to avoid racing the monitor thread.
        with self.database._lock:
            if self.database._closed:
                raise RuntimeError("Database is closed")
            self.connection.executescript(schema.read_text(encoding="utf-8"))

    @staticmethod
    def _amount(value, allow_zero=False):
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("Invalid monetary amount")

        if not amount.is_finite():
            raise ValueError("Amount must be finite")
        if amount < 0 or (amount == 0 and not allow_zero):
            raise ValueError("Amount must be positive")
        return amount

    def _ledger_account(self, account_id, code):
        row = self.connection.execute(
            """
            SELECT id FROM ledger_accounts
            WHERE account_id = ? AND account_code = ? AND asset_code = 'USDT'
            """,
            (account_id, code),
        ).fetchone()

        if row is None:
            raise ValueError("Ledger account not found")
        return row["id"]

    def _post_entry(self, account_id, event_type, reference, amount):
        cash_id = self._ledger_account(account_id, "CASH")
        equity_id = self._ledger_account(account_id, "CAPITAL")

        entry_id = f"{event_type.lower()}:{reference}"

        self.connection.execute(
            """
            INSERT INTO journal_entries
                (id, account_id, event_type, reference_id,
                 idempotency_key, status, description)
            VALUES (?, ?, ?, ?, ?, 'DRAFT', ?)
            """,
            (
                entry_id,
                account_id,
                event_type,
                reference,
                entry_id,
                f"{event_type} {reference}",
            ),
        )

        self.connection.execute(
            """
            INSERT INTO journal_lines
                (entry_id, ledger_account_id, asset_code, debit, credit)
            VALUES (?, ?, 'USDT', ?, '0')
            """,
            (entry_id, cash_id, str(amount)),
        )

        self.connection.execute(
            """
            INSERT INTO journal_lines
                (entry_id, ledger_account_id, asset_code, debit, credit)
            VALUES (?, ?, 'USDT', '0', ?)
            """,
            (entry_id, equity_id, str(amount)),
        )

        self.connection.execute(
            """
            UPDATE journal_entries
            SET status = 'POSTED', posted_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (entry_id,),
        )

        return entry_id

    def create_account(self, account_id, initial_balance):
        if not isinstance(account_id, str) or not account_id.strip():
            raise ValueError("Invalid account ID")

        account_id = account_id.strip()
        balance = self._amount(initial_balance, allow_zero=True)

        with self.database.transaction():
            self.connection.execute(
                """
                INSERT INTO demo_accounts (account_id, initial_capital)
                VALUES (?, ?)
                """,
                (account_id, str(balance)),
            )

            self.connection.executemany(
                """
                INSERT INTO ledger_accounts
                    (account_id, account_code, account_name,
                     account_type, asset_code)
                VALUES (?, ?, ?, ?, 'USDT')
                """,
                [
                    (account_id, "CASH", "Available Cash", "ASSET"),
                    (account_id, "CAPITAL", "Owner Capital", "EQUITY"),
                ],
            )

            if balance > 0:
                self._post_entry(
                    account_id,
                    "OPENING",
                    f"opening:{account_id}",
                    balance,
                )

    def get_balance(self, account_id):
        cash_id = self._ledger_account(account_id, "CASH")

        rows = self.connection.execute(
            """
            SELECT debit, credit
            FROM journal_lines
            WHERE ledger_account_id = ? AND asset_code = 'USDT'
            """,
            (cash_id,),
        ).fetchall()

        balance = sum(
            (Decimal(row["debit"]) - Decimal(row["credit"]) for row in rows),
            Decimal("0"),
        )
        return balance

    def deposit(self, account_id, amount, reference):
        amount = self._amount(amount)

        if not isinstance(reference, str) or not reference.strip():
            raise ValueError("A unique reference is required")

        reference = reference.strip()

        try:
            with self.database.transaction():
                exists = self.connection.execute(
                    "SELECT 1 FROM demo_accounts WHERE account_id = ?",
                    (account_id,),
                ).fetchone()

                if exists is None:
                    raise ValueError("Account not found")

                self._post_entry(
                    account_id,
                    "DEPOSIT",
                    reference,
                    amount,
                )

        except sqlite3.IntegrityError as exc:
            raise ValueError("Duplicate transaction reference") from exc

        return self.get_balance(account_id)

    def get_transactions(self, account_id):
        account = self.connection.execute(
            """
            SELECT initial_capital FROM demo_accounts
            WHERE account_id = ?
            """,
            (account_id,),
        ).fetchone()

        if account is None:
            raise ValueError("Account not found")

        rows = self.connection.execute(
            """
            SELECT
                e.id,
                e.account_id,
                e.event_type,
                e.reference_id,
                e.created_at,
                l.debit
            FROM journal_entries e
            JOIN journal_lines l ON l.entry_id = e.id
            JOIN ledger_accounts a ON a.id = l.ledger_account_id
            WHERE e.account_id = ?
              AND e.event_type = 'DEPOSIT'
              AND e.status = 'POSTED'
              AND a.account_code = 'CASH'
            ORDER BY e.created_at ASC, e.id ASC
            """,
            (account_id,),
        ).fetchall()

        balance = Decimal(account["initial_capital"])
        transactions = []

        for row in rows:
            amount = Decimal(row["debit"])
            balance += amount

            transactions.append(
                {
                    "id": row["id"],
                    "account_id": row["account_id"],
                    "type": row["event_type"],
                    "amount": amount,
                    "balance_after": balance,
                    "reference": row["reference_id"],
                    "created_at": row["created_at"],
                }
            )

        return transactions

    def close(self):
        if self._owns_database:
            self.database.close()
