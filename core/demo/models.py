from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Optional
from datetime import datetime, timezone


class MarketType(str, Enum):
    SPOT = "SPOT"
    FUTURES = "FUTURES"
    ALPHA = "ALPHA"


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class PositionDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


def _decimal(value, name, allow_zero=False, allow_negative=False):
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{name} must be a valid decimal")

    if not result.is_finite():
        raise ValueError(f"{name} must be finite")

    if not allow_negative and result < 0:
        raise ValueError(f"{name} cannot be negative")

    if result == 0 and not allow_zero:
        raise ValueError(f"{name} must be positive")

    return result


def _required_text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


@dataclass
class OrderRequest:
    order_id: str
    agent_id: str
    symbol: str
    market_type: MarketType
    side: Side
    quantity: Decimal
    order_type: str = "MARKET"
    leverage: Decimal = Decimal("1")
    status: OrderStatus = OrderStatus.PENDING
    limit_price: Optional[Decimal] = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def __post_init__(self):
        self.order_id = _required_text(self.order_id, "order_id")
        self.agent_id = _required_text(self.agent_id, "agent_id")
        self.symbol = _required_text(self.symbol, "symbol").upper()

        if not isinstance(self.market_type, MarketType):
            raise ValueError("Invalid market_type")

        if not isinstance(self.side, Side):
            raise ValueError("Invalid side")

        if not isinstance(self.status, OrderStatus):
            raise ValueError("Invalid order status")

        self.quantity = _decimal(self.quantity, "quantity")
        self.leverage = _decimal(self.leverage, "leverage")

        self.order_type = _required_text(
            self.order_type, "order_type"
        ).upper()

        if self.limit_price is not None:
            self.limit_price = _decimal(
                self.limit_price, "limit_price"
            )

        if self.market_type == MarketType.SPOT and self.leverage != 1:
            raise ValueError("Spot orders must use leverage 1")


@dataclass
class Position:
    position_id: str
    agent_id: str
    symbol: str
    market_type: MarketType
    direction: PositionDirection
    quantity: Decimal
    entry_price: Decimal
    mark_price: Decimal
    leverage: Decimal = Decimal("1")
    opened_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    realized_pnl: Decimal = Decimal("0")
    fees_paid: Decimal = Decimal("0")
    is_open: bool = True

    def __post_init__(self):
        self.position_id = _required_text(
            self.position_id, "position_id"
        )
        self.agent_id = _required_text(self.agent_id, "agent_id")
        self.symbol = _required_text(self.symbol, "symbol").upper()

        if not isinstance(self.market_type, MarketType):
            raise ValueError("Invalid market_type")

        if not isinstance(self.direction, PositionDirection):
            raise ValueError("Invalid position direction")

        self.quantity = _decimal(self.quantity, "quantity")
        self.entry_price = _decimal(self.entry_price, "entry_price")
        self.mark_price = _decimal(self.mark_price, "mark_price")
        self.leverage = _decimal(self.leverage, "leverage")
        self.realized_pnl = _decimal(
            self.realized_pnl,
            "realized_pnl",
            allow_zero=True,
            allow_negative=True,
        )
        self.fees_paid = _decimal(
            self.fees_paid, "fees_paid", allow_zero=True
        )

        if self.market_type == MarketType.SPOT:
            if self.direction != PositionDirection.LONG:
                raise ValueError("Spot positions cannot be short")
            if self.leverage != 1:
                raise ValueError("Spot positions must use leverage 1")

    def unrealized_pnl(self):
        if self.direction == PositionDirection.LONG:
            return (self.mark_price - self.entry_price) * self.quantity

        return (self.entry_price - self.mark_price) * self.quantity

    def notional_value(self):
        return self.mark_price * self.quantity

    def initial_margin(self):
        return self.entry_price * self.quantity / self.leverage

    def equity_contribution(self):
        return self.initial_margin() + self.unrealized_pnl()
