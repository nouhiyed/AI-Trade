from decimal import Decimal
import pytest

from core.demo.models import (
    MarketType,
    Side,
    PositionDirection,
    OrderStatus,
    OrderRequest,
    Position,
)


D = Decimal


def test_market_type_values():
    assert MarketType.SPOT.value == "SPOT"
    assert MarketType.FUTURES.value == "FUTURES"
    assert MarketType.ALPHA.value == "ALPHA"


def test_side_values():
    assert Side.BUY.value == "BUY"
    assert Side.SELL.value == "SELL"


def test_position_direction_values():
    assert PositionDirection.LONG.value == "LONG"
    assert PositionDirection.SHORT.value == "SHORT"


def test_order_status_values():
    assert OrderStatus.PENDING.value == "PENDING"
    assert OrderStatus.FILLED.value == "FILLED"
    assert OrderStatus.CANCELLED.value == "CANCELLED"
    assert OrderStatus.REJECTED.value == "REJECTED"


def test_order_request_preserves_decimal_values():
    order = OrderRequest(
        order_id="order-1",
        agent_id="futures",
        symbol="BTCUSDT",
        market_type=MarketType.FUTURES,
        side=Side.BUY,
        quantity=D("0.01"),
        order_type="MARKET",
        leverage=D("5"),
    )

    assert order.quantity == D("0.01")
    assert order.leverage == D("5")
    assert order.status == OrderStatus.PENDING


def test_order_rejects_invalid_quantity():
    with pytest.raises(ValueError):
        OrderRequest(
            order_id="order-2",
            agent_id="spot",
            symbol="BTCUSDT",
            market_type=MarketType.SPOT,
            side=Side.BUY,
            quantity=D("0"),
        )


def test_position_calculates_long_unrealized_pnl():
    position = Position(
        position_id="position-1",
        agent_id="futures",
        symbol="BTCUSDT",
        market_type=MarketType.FUTURES,
        direction=PositionDirection.LONG,
        quantity=D("0.1"),
        entry_price=D("60000"),
        mark_price=D("61000"),
        leverage=D("5"),
    )

    assert position.unrealized_pnl() == D("100")


def test_position_calculates_short_unrealized_pnl():
    position = Position(
        position_id="position-2",
        agent_id="futures",
        symbol="BTCUSDT",
        market_type=MarketType.FUTURES,
        direction=PositionDirection.SHORT,
        quantity=D("0.1"),
        entry_price=D("60000"),
        mark_price=D("59000"),
        leverage=D("5"),
    )

    assert position.unrealized_pnl() == D("100")


def test_position_rejects_invalid_quantity():
    with pytest.raises(ValueError):
        Position(
            position_id="position-3",
            agent_id="spot",
            symbol="BTCUSDT",
            market_type=MarketType.SPOT,
            direction=PositionDirection.LONG,
            quantity=D("-1"),
            entry_price=D("60000"),
            mark_price=D("60000"),
            leverage=D("1"),
        )


def test_position_accepts_positive_realized_pnl():
    position = Position(
        position_id="position-profit",
        agent_id="futures",
        symbol="BTCUSDT",
        market_type=MarketType.FUTURES,
        direction=PositionDirection.LONG,
        quantity=D("0.1"),
        entry_price=D("60000"),
        mark_price=D("61000"),
        leverage=D("5"),
        realized_pnl=D("25"),
    )

    assert position.realized_pnl == D("25")


def test_position_accepts_negative_realized_pnl():
    position = Position(
        position_id="position-loss",
        agent_id="futures",
        symbol="BTCUSDT",
        market_type=MarketType.FUTURES,
        direction=PositionDirection.LONG,
        quantity=D("0.1"),
        entry_price=D("60000"),
        mark_price=D("59000"),
        leverage=D("5"),
        realized_pnl=D("-25"),
    )

    assert position.realized_pnl == D("-25")
