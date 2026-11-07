import sqlite3
from pathlib import Path

import pytest

from core.demo.database import DemoDatabase


SCHEMA = Path("core/demo/schema.sql")


@pytest.fixture
def db(tmp_path):
    database = DemoDatabase(tmp_path / "integrity.db")
    database.connection.executescript(SCHEMA.read_text())
    yield database
    database.close()


def create_accounts(db):
    conn = db.connection

    conn.execute(
        """INSERT INTO demo_accounts (account_id, initial_capital)
           VALUES ('main', '1000')"""
    )

    accounts = {}
    for code, asset in (
        ("CASH", "USDT"),
        ("RECEIVABLE", "USDT"),
        ("BTC_ASSET", "BTC"),
        ("BTC_CLEARING", "BTC"),
    ):
        cursor = conn.execute(
            """INSERT INTO ledger_accounts
               (account_id, account_code, account_name, account_type, asset_code)
               VALUES ('main', ?, ?, 'ASSET', ?)""",
            (code, code, asset),
        )
        accounts[code] = cursor.lastrowid

    return accounts


def create_entry(db, entry_id="entry-1"):
    db.connection.execute(
        """INSERT INTO journal_entries
           (id, account_id, event_type, idempotency_key, status)
           VALUES (?, 'main', 'TEST', ?, 'DRAFT')""",
        (entry_id, f"key-{entry_id}"),
    )


def add_line(db, entry_id, account_id, asset, debit, credit):
    db.connection.execute(
        """INSERT INTO journal_lines
           (entry_id, ledger_account_id, asset_code, debit, credit)
           VALUES (?, ?, ?, ?, ?)""",
        (entry_id, account_id, asset, str(debit), str(credit)),
    )


def post_entry(db, entry_id="entry-1"):
    db.connection.execute(
        "UPDATE journal_entries SET status = 'POSTED' WHERE id = ?",
        (entry_id,),
    )


def test_balanced_entry_can_be_posted(db):
    accounts = create_accounts(db)
    create_entry(db)

    add_line(db, "entry-1", accounts["CASH"], "USDT", "100.25", "0")
    add_line(db, "entry-1", accounts["RECEIVABLE"], "USDT", "0", "100.25")

    post_entry(db)

    status = db.connection.execute(
        "SELECT status FROM journal_entries WHERE id = 'entry-1'"
    ).fetchone()["status"]

    assert status == "POSTED"


def test_unbalanced_entry_cannot_be_posted(db):
    accounts = create_accounts(db)
    create_entry(db)

    add_line(db, "entry-1", accounts["CASH"], "USDT", "100", "0")
    add_line(db, "entry-1", accounts["RECEIVABLE"], "USDT", "0", "90")

    with pytest.raises(sqlite3.IntegrityError):
        post_entry(db)

    status = db.connection.execute(
        "SELECT status FROM journal_entries WHERE id = 'entry-1'"
    ).fetchone()["status"]

    assert status == "DRAFT"


@pytest.mark.parametrize("line_count", [0, 1])
def test_entry_with_fewer_than_two_lines_cannot_be_posted(db, line_count):
    accounts = create_accounts(db)
    create_entry(db)

    if line_count == 1:
        add_line(db, "entry-1", accounts["CASH"], "USDT", "100", "0")

    with pytest.raises(sqlite3.IntegrityError):
        post_entry(db)


def test_each_asset_must_balance_independently(db):
    accounts = create_accounts(db)
    create_entry(db)

    add_line(db, "entry-1", accounts["CASH"], "USDT", "100", "0")
    add_line(db, "entry-1", accounts["RECEIVABLE"], "USDT", "0", "100")

    add_line(db, "entry-1", accounts["BTC_ASSET"], "BTC", "2", "0")
    add_line(db, "entry-1", accounts["BTC_CLEARING"], "BTC", "0", "1")

    with pytest.raises(sqlite3.IntegrityError):
        post_entry(db)


@pytest.mark.parametrize(
    ("debit", "credit"),
    [
        ("-1", "0"),
        ("NaN", "0"),
        ("Infinity", "0"),
        ("-Infinity", "0"),
        ("10", "5"),
        ("0", "0"),
    ],
)
def test_invalid_journal_line_amounts_are_rejected(db, debit, credit):
    accounts = create_accounts(db)
    create_entry(db)

    with pytest.raises(sqlite3.IntegrityError):
        add_line(
            db, "entry-1", accounts["CASH"], "USDT", debit, credit
        )


def test_posted_journal_lines_cannot_be_modified(db):
    accounts = create_accounts(db)
    create_entry(db)

    add_line(db, "entry-1", accounts["CASH"], "USDT", "50", "0")
    add_line(db, "entry-1", accounts["RECEIVABLE"], "USDT", "0", "50")
    post_entry(db)

    with pytest.raises(sqlite3.IntegrityError):
        db.connection.execute(
            "UPDATE journal_lines SET debit = '60' WHERE entry_id = 'entry-1' AND debit <> '0'"
        )
