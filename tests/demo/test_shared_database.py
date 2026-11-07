import sqlite3
from decimal import Decimal

import pytest

from core.demo.database import DemoDatabase
from core.demo.ledger import Ledger
from core.demo.storage import DemoStorage
from core.demo.models import (
    MarketType,
    PositionDirection,
    Position,
)

D = Decimal


def make_position():
    return Position(
        position_id="pos-atomic-1",
        agent_id="futures",
        symbol="BTCUSDT",
        market_type=MarketType.FUTURES,
        direction=PositionDirection.LONG,
        quantity=D("0.1"),
        entry_price=D("60000"),
        mark_price=D("60000"),
        leverage=D("5"),
    )


def test_balance_and_position_rollback_together(tmp_path):
    db = DemoDatabase(tmp_path / "shared.db")
    ledger = Ledger(database=db)
    storage = DemoStorage(database=db)

    ledger.create_account("main", D("1000"))

    db.connection.execute("""
        CREATE TRIGGER reject_position
        BEFORE INSERT ON demo_positions
        BEGIN
            SELECT RAISE(ABORT, 'forced position failure');
        END
    """)

    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction():
            ledger.deposit(
                "main",
                D("200"),
                "atomic-deposit-1",
            )
            storage.save_position(make_position())

    assert ledger.get_balance("main") == D("1000")
    assert ledger.get_transactions("main") == []
    assert storage.get_position("pos-atomic-1") is None

    ledger.close()
    storage.close()
    db.close()


def test_balance_and_position_commit_together(tmp_path):
    db = DemoDatabase(tmp_path / "shared.db")
    ledger = Ledger(database=db)
    storage = DemoStorage(database=db)

    ledger.create_account("main", D("1000"))

    with db.transaction():
        ledger.deposit(
            "main",
            D("200"),
            "atomic-deposit-2",
        )
        storage.save_position(make_position())

    assert ledger.get_balance("main") == D("1200")
    assert len(ledger.get_transactions("main")) == 1
    assert storage.get_position("pos-atomic-1") is not None

    ledger.close()
    storage.close()
    db.close()
