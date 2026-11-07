from decimal import Decimal
import pytest

from core.demo.ledger import Ledger
from core.demo.models import (
    MarketType,
    PositionDirection,
    Position,
)


D = Decimal


def test_ledger_recovery_preserves_balance_and_history(tmp_path):
    db = tmp_path / "recovery.db"

    ledger = Ledger(db)
    ledger.create_account("main", D("1000"))
    ledger.deposit("main", D("200"), reference="recovery-1")
    ledger.close()

    recovered = Ledger(db)

    assert recovered.get_balance("main") == D("1200")
    assert len(recovered.get_transactions("main")) == 1

    recovered.close()


def test_recovery_does_not_duplicate_transactions(tmp_path):
    db = tmp_path / "recovery.db"

    ledger = Ledger(db)
    ledger.create_account("main", D("1000"))
    ledger.deposit("main", D("100"), reference="unique-recovery")
    ledger.close()

    recovered = Ledger(db)

    with pytest.raises(ValueError):
        recovered.deposit(
            "main", D("100"), reference="unique-recovery"
        )

    assert recovered.get_balance("main") == D("1100")
    assert len(recovered.get_transactions("main")) == 1

    recovered.close()


def test_position_can_be_reconstructed_after_restart():
    original = Position(
        position_id="position-recovery-1",
        agent_id="futures",
        symbol="BTCUSDT",
        market_type=MarketType.FUTURES,
        direction=PositionDirection.LONG,
        quantity=D("0.1"),
        entry_price=D("60000"),
        mark_price=D("61000"),
        leverage=D("5"),
    )

    recovered = Position(**{
        "position_id": original.position_id,
        "agent_id": original.agent_id,
        "symbol": original.symbol,
        "market_type": MarketType(original.market_type.value),
        "direction": PositionDirection(original.direction.value),
        "quantity": D(str(original.quantity)),
        "entry_price": D(str(original.entry_price)),
        "mark_price": D(str(original.mark_price)),
        "leverage": D(str(original.leverage)),
        "realized_pnl": D(str(original.realized_pnl)),
        "fees_paid": D(str(original.fees_paid)),
        "is_open": original.is_open,
    })

    assert recovered.position_id == original.position_id
    assert recovered.unrealized_pnl() == D("100")
    assert recovered.is_open is True
