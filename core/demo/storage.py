from datetime import datetime
from decimal import Decimal
from pathlib import Path

from core.demo.database import DemoDatabase
from core.demo.models import (
    MarketType,
    PositionDirection,
    Position,
    OrderRequest,
    Side,
    OrderStatus,
)


class DemoStorage:
    def __init__(self, db_path=None, *, database=None):
        if (db_path is None) == (database is None):
            raise ValueError("Provide exactly one of db_path or database")

        self._owns_database = database is None

        if self._owns_database:
            self.database = DemoDatabase(Path(db_path))
        else:
            if not isinstance(database, DemoDatabase):
                raise TypeError("database must be a DemoDatabase")
            self.database = database

        self.connection = self.database.connection
        self._initialize()

    def _initialize(self):
        with self.database.transaction():
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS demo_positions (
                    position_id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    market_type TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    quantity TEXT NOT NULL,
                    entry_price TEXT NOT NULL,
                    mark_price TEXT NOT NULL,
                    leverage TEXT NOT NULL,
                    opened_at TEXT NOT NULL,
                    realized_pnl TEXT NOT NULL,
                    fees_paid TEXT NOT NULL,
                    is_open INTEGER NOT NULL
                )
            """)

            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS demo_orders (
                    order_id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    market_type TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    leverage TEXT NOT NULL,
                    status TEXT NOT NULL,
                    limit_price TEXT,
                    created_at TEXT NOT NULL
                )
            """)

    @staticmethod
    def _position_from_row(row):
        return Position(
            position_id=row["position_id"],
            agent_id=row["agent_id"],
            symbol=row["symbol"],
            market_type=MarketType(row["market_type"]),
            direction=PositionDirection(row["direction"]),
            quantity=Decimal(row["quantity"]),
            entry_price=Decimal(row["entry_price"]),
            mark_price=Decimal(row["mark_price"]),
            leverage=Decimal(row["leverage"]),
            opened_at=datetime.fromisoformat(row["opened_at"]),
            realized_pnl=Decimal(row["realized_pnl"]),
            fees_paid=Decimal(row["fees_paid"]),
            is_open=bool(row["is_open"]),
        )

    @staticmethod
    def _order_from_row(row):
        return OrderRequest(
            order_id=row["order_id"],
            agent_id=row["agent_id"],
            symbol=row["symbol"],
            market_type=MarketType(row["market_type"]),
            side=Side(row["side"]),
            quantity=Decimal(row["quantity"]),
            order_type=row["order_type"],
            leverage=Decimal(row["leverage"]),
            status=OrderStatus(row["status"]),
            limit_price=(
                Decimal(row["limit_price"])
                if row["limit_price"] is not None
                else None
            ),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def save_position(self, position):
        if not isinstance(position, Position):
            raise TypeError("position must be a Position")

        with self.database.transaction():
            self.connection.execute("""
                INSERT INTO demo_positions (
                    position_id, agent_id, symbol, market_type,
                    direction, quantity, entry_price, mark_price,
                    leverage, opened_at, realized_pnl, fees_paid,
                    is_open
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(position_id) DO UPDATE SET
                    agent_id=excluded.agent_id,
                    symbol=excluded.symbol,
                    market_type=excluded.market_type,
                    direction=excluded.direction,
                    quantity=excluded.quantity,
                    entry_price=excluded.entry_price,
                    mark_price=excluded.mark_price,
                    leverage=excluded.leverage,
                    opened_at=excluded.opened_at,
                    realized_pnl=excluded.realized_pnl,
                    fees_paid=excluded.fees_paid,
                    is_open=excluded.is_open
            """, (
                position.position_id,
                position.agent_id,
                position.symbol,
                position.market_type.value,
                position.direction.value,
                str(position.quantity),
                str(position.entry_price),
                str(position.mark_price),
                str(position.leverage),
                position.opened_at.isoformat(),
                str(position.realized_pnl),
                str(position.fees_paid),
                int(position.is_open),
            ))

    def get_position(self, position_id):
        row = self.connection.execute(
            "SELECT * FROM demo_positions WHERE position_id = ?",
            (position_id,),
        ).fetchone()

        return self._position_from_row(row) if row else None

    def get_open_positions(self, agent_id=None):
        if agent_id is None:
            rows = self.connection.execute("""
                SELECT * FROM demo_positions
                WHERE is_open = 1
                ORDER BY opened_at ASC
            """).fetchall()
        else:
            rows = self.connection.execute("""
                SELECT * FROM demo_positions
                WHERE is_open = 1 AND agent_id = ?
                ORDER BY opened_at ASC
            """, (agent_id,)).fetchall()

        return [self._position_from_row(row) for row in rows]

    def save_order(self, order):
        if not isinstance(order, OrderRequest):
            raise TypeError("order must be an OrderRequest")

        with self.database.transaction():
            self.connection.execute("""
                INSERT INTO demo_orders (
                    order_id, agent_id, symbol, market_type,
                    side, quantity, order_type, leverage,
                    status, limit_price, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(order_id) DO UPDATE SET
                    status=excluded.status,
                    quantity=excluded.quantity,
                    limit_price=excluded.limit_price
            """, (
                order.order_id,
                order.agent_id,
                order.symbol,
                order.market_type.value,
                order.side.value,
                str(order.quantity),
                order.order_type,
                str(order.leverage),
                order.status.value,
                (
                    str(order.limit_price)
                    if order.limit_price is not None
                    else None
                ),
                order.created_at.isoformat(),
            ))

    def get_order(self, order_id):
        row = self.connection.execute(
            "SELECT * FROM demo_orders WHERE order_id = ?",
            (order_id,),
        ).fetchone()

        return self._order_from_row(row) if row else None

    def close(self):
        if self._owns_database:
            self.database.close()
