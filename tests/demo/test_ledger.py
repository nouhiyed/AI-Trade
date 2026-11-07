from decimal import Decimal

import pytest

from core.demo.ledger import Ledger


D = Decimal


def test_create_account_and_read_balance(tmp_path):
    ledger = Ledger(tmp_path / "demo.db")
    ledger.create_account("main", D("1000"))

    assert ledger.get_balance("main") == D("1000")


def test_deposit_updates_balance_and_history(tmp_path):
    ledger = Ledger(tmp_path / "demo.db")
    ledger.create_account("main", D("1000"))

    ledger.deposit("main", D("250"), reference="deposit-1")

    assert ledger.get_balance("main") == D("1250")
    assert len(ledger.get_transactions("main")) == 1


def test_duplicate_reference_is_rejected(tmp_path):
    ledger = Ledger(tmp_path / "demo.db")
    ledger.create_account("main", D("1000"))

    ledger.deposit("main", D("100"), reference="unique-1")

    with pytest.raises((ValueError, RuntimeError)):
        ledger.deposit("main", D("100"), reference="unique-1")


@pytest.mark.parametrize("amount", [
    D("0"),
    D("-1"),
    D("NaN"),
    D("Infinity"),
])
def test_invalid_deposit_is_rejected(tmp_path, amount):
    ledger = Ledger(tmp_path / "demo.db")
    ledger.create_account("main", D("1000"))

    with pytest.raises((ValueError, ArithmeticError)):
        ledger.deposit("main", amount, reference="invalid")


def test_account_survives_reopening_database(tmp_path):
    db_path = tmp_path / "demo.db"

    ledger1 = Ledger(db_path)
    ledger1.create_account("main", D("500"))
    ledger1.deposit("main", D("75"), reference="deposit-2")
    ledger1.close()

    ledger2 = Ledger(db_path)

    assert ledger2.get_balance("main") == D("575")
    assert len(ledger2.get_transactions("main")) == 1

    ledger2.close()


def test_shared_database_deposit_rolls_back_with_outer_transaction(tmp_path):
    from core.demo.database import DemoDatabase

    db = DemoDatabase(tmp_path / "shared.db")
    ledger = Ledger(database=db)
    ledger.create_account("main", D("1000"))

    with pytest.raises(RuntimeError):
        with db.transaction():
            ledger.deposit("main", D("200"), "shared-deposit-1")
            raise RuntimeError("force outer rollback")

    assert ledger.get_balance("main") == D("1000")
    assert ledger.get_transactions("main") == []

    ledger.close()
    assert db.connection.execute("SELECT 1").fetchone()[0] == 1
    db.close()


def test_shared_database_nested_deposit_commits_with_outer_transaction(tmp_path):
    from core.demo.database import DemoDatabase

    db = DemoDatabase(tmp_path / "shared.db")
    ledger = Ledger(database=db)
    ledger.create_account("main", D("1000"))

    with db.transaction():
        ledger.deposit("main", D("200"), "shared-deposit-2")

    assert ledger.get_balance("main") == D("1200")
    assert len(ledger.get_transactions("main")) == 1

    ledger.close()
    db.close()
