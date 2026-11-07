from decimal import Decimal

from core.demo.models import (
    MarketType,
    PositionDirection,
    Position,
    OrderRequest,
    Side,
    OrderStatus,
)
from core.demo.storage import DemoStorage


D = Decimal


def make_position():
    return Position(
        position_id="pos-1",
        agent_id="futures",
        symbol="BTCUSDT",
        market_type=MarketType.FUTURES,
        direction=PositionDirection.LONG,
        quantity=D("0.1"),
        entry_price=D("60000"),
        mark_price=D("61000"),
        leverage=D("5"),
    )


def make_order():
    return OrderRequest(
        order_id="order-1",
        agent_id="futures",
        symbol="BTCUSDT",
        market_type=MarketType.FUTURES,
        side=Side.BUY,
        quantity=D("0.1"),
        leverage=D("5"),
    )


def test_save_and_load_position(tmp_path):
    storage = DemoStorage(tmp_path / "demo.db")
    position = make_position()

    storage.save_position(position)
    loaded = storage.get_position("pos-1")

    assert loaded.position_id == position.position_id
    assert loaded.quantity == D("0.1")
    assert loaded.unrealized_pnl() == D("100")

    storage.close()


def test_save_and_load_order(tmp_path):
    storage = DemoStorage(tmp_path / "demo.db")
    order = make_order()

    storage.save_order(order)
    loaded = storage.get_order("order-1")

    assert loaded.order_id == order.order_id
    assert loaded.quantity == D("0.1")
    assert loaded.status == OrderStatus.PENDING

    storage.close()


def test_position_survives_database_reopening(tmp_path):
    db = tmp_path / "demo.db"

    storage = DemoStorage(db)
    storage.save_position(make_position())
    storage.close()

    recovered = DemoStorage(db)
    loaded = recovered.get_position("pos-1")

    assert loaded.symbol == "BTCUSDT"
    assert loaded.entry_price == D("60000")
    assert loaded.unrealized_pnl() == D("100")

    recovered.close()


def test_open_positions_can_be_listed(tmp_path):
    storage = DemoStorage(tmp_path / "demo.db")

    storage.save_position(make_position())

    positions = storage.get_open_positions()

    assert len(positions) == 1
    assert positions[0].position_id == "pos-1"

    storage.close()
