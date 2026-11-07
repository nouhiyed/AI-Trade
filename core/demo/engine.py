from decimal import Decimal, InvalidOperation
from uuid import uuid4

from core.demo.accounting import (
    calculate_fee,
    calculate_fill_price,
    calculate_futures_pnl,
    calculate_initial_margin,
)
from core.demo.database import DemoDatabase
from core.demo.ledger import Ledger
from core.demo.models import MarketType, Side


class DemoEngine:
    """Local DEMO execution engine. Never sends orders to an exchange."""

    def __init__(
        self,
        database,
        ledger,
        *,
        fee_rate=Decimal("0.001"),
        slippage_rate=Decimal("0.0005"),
    ):
        if not isinstance(database, DemoDatabase):
            raise TypeError("database must be a DemoDatabase")
        if not isinstance(ledger, Ledger):
            raise TypeError("ledger must be a Ledger")
        if ledger.database is not database:
            raise ValueError("Engine and Ledger must share one database")

        self.database = database
        self.connection = database.connection
        self.ledger = ledger
        self.fee_rate = self._decimal(fee_rate, "fee_rate")
        self.slippage_rate = self._decimal(
            slippage_rate, "slippage_rate"
        )

        if self.fee_rate < 0 or self.slippage_rate < 0:
            raise ValueError("Rates cannot be negative")
        if self.slippage_rate >= 1:
            raise ValueError("slippage_rate must be less than 1")

    @staticmethod
    def _decimal(value, name, positive=False):
        try:
            result = (
                value if isinstance(value, Decimal)
                else Decimal(str(value))
            )
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError(f"Invalid {name}")

        if not result.is_finite():
            raise ValueError(f"{name} must be finite")
        if positive and result <= 0:
            raise ValueError(f"{name} must be greater than zero")
        return result

    @staticmethod
    def _asset(symbol):
        symbol = str(symbol).upper().strip()
        if not symbol.endswith("USDT") or len(symbol) <= 4:
            raise ValueError("Only USDT-quoted symbols are supported")
        return symbol[:-4]

    def create_account(self, account_id, initial_capital):
        self.ledger.create_account(account_id, initial_capital)
        return self.get_account_summary(account_id)

    def _account(self, account_id):
        row = self.connection.execute(
            """
            SELECT account_id, status, quote_asset
            FROM demo_accounts WHERE account_id = ?
            """,
            (account_id,),
        ).fetchone()

        if row is None:
            raise ValueError("DEMO account not found")
        if row["status"] != "ACTIVE":
            raise ValueError("DEMO account is not active")
        return row

    def _ledger_account(self, account_id, code, asset, account_type):
        self.connection.execute(
            """
            INSERT OR IGNORE INTO ledger_accounts
                (account_id, account_code, account_name,
                 account_type, asset_code)
            VALUES (?, ?, ?, ?, ?)
            """,
            (account_id, code, code.replace("_", " ").title(),
             account_type, asset),
        )
        row = self.connection.execute(
            """
            SELECT id FROM ledger_accounts
            WHERE account_id = ? AND account_code = ?
              AND asset_code = ?
            """,
            (account_id, code, asset),
        ).fetchone()
        return row["id"]

    def _post(self, account_id, event_type, reference, lines):
        """Post balanced journal lines, independently for each asset."""
        entry_id = f"{event_type.lower()}:{account_id}:{reference}"

        existing = self.connection.execute(
            "SELECT id FROM journal_entries WHERE id = ?",
            (entry_id,),
        ).fetchone()
        if existing:
            raise ValueError("Duplicate accounting reference")

        self.connection.execute(
            """
            INSERT INTO journal_entries
                (id, account_id, event_type, reference_id,
                 idempotency_key, status, description)
            VALUES (?, ?, ?, ?, ?, 'DRAFT', ?)
            """,
            (
                entry_id, account_id, event_type, reference,
                entry_id, f"{event_type} {reference}",
            ),
        )

        for code, asset, debit, credit, account_type in lines:
            ledger_id = self._ledger_account(
                account_id, code, asset, account_type
            )
            self.connection.execute(
                """
                INSERT INTO journal_lines
                    (entry_id, ledger_account_id, asset_code, debit, credit)
                VALUES (?, ?, ?, ?, ?)
                """,
                (entry_id, ledger_id, asset, str(debit), str(credit)),
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

    def _cash(self, account_id):
        return self.ledger.get_balance(account_id)

    def _record_order(
        self, account_id, order_id, agent_id, symbol,
        market_type, side, quantity, order_type="MARKET",
        limit_price=None,
    ):
        self.connection.execute(
            """
            INSERT INTO orders
                (order_id, account_id, agent_id, symbol, market_type,
                 side, order_type, quantity, limit_price, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
            """,
            (
                order_id, account_id, agent_id, symbol,
                market_type, side, order_type, str(quantity),
                str(limit_price) if limit_price is not None else None,
            ),
        )

    def _record_fill(
        self, order_id, price, quantity, fee, asset, slippage
    ):
        fill_id = uuid4().hex
        self.connection.execute(
            """
            INSERT INTO fills
                (fill_id, order_id, execution_price, quantity,
                 fee_amount, fee_asset, slippage_amount)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fill_id, order_id, str(price), str(quantity),
                str(fee), asset, str(slippage),
            ),
        )
        self.connection.execute(
            """
            UPDATE orders
            SET status = 'FILLED',
                filled_quantity = ?,
                average_fill_price = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE order_id = ?
            """,
            (str(quantity), str(price), order_id),
        )
        return fill_id

    def _spot_buy(
        self, account_id, agent_id, symbol, quantity,
        price, order_id,
    ):
        asset = self._asset(symbol)
        fill_price = calculate_fill_price(
            price, "BUY", self.slippage_rate
        )
        notional = fill_price * quantity
        fee = calculate_fee(fill_price, quantity, self.fee_rate)
        total = notional + fee

        if self._cash(account_id) < total:
            raise ValueError("Insufficient DEMO cash balance")

        inventory = self.connection.execute(
            """
            SELECT quantity, average_cost FROM spot_inventory
            WHERE account_id = ? AND agent_id = ? AND asset_code = ?
            """,
            (account_id, agent_id, asset),
        ).fetchone()

        old_qty = Decimal(inventory["quantity"]) if inventory else Decimal("0")
        old_cost = Decimal(inventory["average_cost"]) if inventory else Decimal("0")
        new_qty = old_qty + quantity
        average_cost = (
            (old_qty * old_cost + notional) / new_qty
        )

        self._post(
            account_id, "SPOT_BUY", order_id,
            [
                ("SPOT_INVENTORY", "USDT", notional, "0", "ASSET"),
                ("CASH", "USDT", "0", notional, "ASSET"),
            ],
        )

        if fee > 0:
            self._post(
                account_id, "TRADING_FEE", f"{order_id}:fee",
                [
                    ("TRADING_FEES", "USDT", fee, "0", "EXPENSE"),
                    ("CASH", "USDT", "0", fee, "ASSET"),
                ],
            )

        self.connection.execute(
            """
            INSERT INTO spot_inventory
                (account_id, agent_id, asset_code, quantity, average_cost)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(account_id, agent_id, asset_code)
            DO UPDATE SET
                quantity = excluded.quantity,
                average_cost = excluded.average_cost,
                updated_at = CURRENT_TIMESTAMP
            """,
            (account_id, agent_id, asset, str(new_qty), str(average_cost)),
        )

        return fill_price, fee, asset

    def _spot_sell(
        self, account_id, agent_id, symbol, quantity,
        price, order_id,
    ):
        asset = self._asset(symbol)
        inventory = self.connection.execute(
            """
            SELECT quantity, average_cost FROM spot_inventory
            WHERE account_id = ? AND agent_id = ? AND asset_code = ?
            """,
            (account_id, agent_id, asset),
        ).fetchone()

        if inventory is None or Decimal(inventory["quantity"]) < quantity:
            raise ValueError("Insufficient DEMO spot inventory")

        fill_price = calculate_fill_price(
            price, "SELL", self.slippage_rate
        )
        proceeds = fill_price * quantity
        fee = calculate_fee(fill_price, quantity, self.fee_rate)
        old_qty = Decimal(inventory["quantity"])
        average_cost = Decimal(inventory["average_cost"])
        cost_basis = average_cost * quantity
        realized = proceeds - fee - cost_basis
        remaining = old_qty - quantity

        sale_lines = [
            ("CASH", "USDT", proceeds, "0", "ASSET"),
        ]
        if proceeds >= cost_basis:
            sale_lines.extend([
                ("SPOT_INVENTORY", "USDT", "0", cost_basis, "ASSET"),
            ])
            gain = proceeds - cost_basis
            if gain > 0:
                sale_lines.append(
                    ("SPOT_REALIZED_PNL", "USDT", "0", gain, "INCOME")
                )
        else:
            loss = cost_basis - proceeds
            sale_lines.extend([
                ("SPOT_REALIZED_PNL", "USDT", loss, "0", "EXPENSE"),
                ("SPOT_INVENTORY", "USDT", "0", cost_basis, "ASSET"),
            ])

        self._post(
            account_id, "SPOT_SELL", order_id, sale_lines
        )

        if fee > 0:
            self._post(
                account_id, "TRADING_FEE", f"{order_id}:fee",
                [
                    ("TRADING_FEES", "USDT", fee, "0", "EXPENSE"),
                    ("CASH", "USDT", "0", fee, "ASSET"),
                ],
            )

        if remaining == 0:
            self.connection.execute(
                """
                DELETE FROM spot_inventory
                WHERE account_id = ? AND agent_id = ? AND asset_code = ?
                """,
                (account_id, agent_id, asset),
            )
        else:
            self.connection.execute(
                """
                UPDATE spot_inventory SET quantity = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE account_id = ? AND agent_id = ? AND asset_code = ?
                """,
                (str(remaining), account_id, agent_id, asset),
            )

        return fill_price, fee, asset, realized

    def submit_order(
        self,
        account_id,
        *,
        agent_id,
        symbol,
        market_type,
        side,
        quantity,
        market_price,
        leverage=Decimal("1"),
        order_id=None,
    ):
        self._account(account_id)
        quantity = self._decimal(quantity, "quantity", positive=True)
        price = self._decimal(market_price, "market_price", positive=True)
        leverage = self._decimal(leverage, "leverage", positive=True)

        if not isinstance(market_type, MarketType):
            market_type = MarketType(str(market_type).upper())
        if not isinstance(side, Side):
            side = Side(str(side).upper())

        if market_type == MarketType.ALPHA:
            raise ValueError("ALPHA execution is not enabled yet")
        if market_type == MarketType.SPOT and leverage != 1:
            raise ValueError("Spot leverage must be 1")

        symbol = str(symbol).upper().strip()
        self._asset(symbol)
        agent_id = str(agent_id).strip()
        if not agent_id:
            raise ValueError("agent_id is required")

        order_id = order_id or uuid4().hex
        fill_price = None
        fee = Decimal("0")
        realized = Decimal("0")

        with self.database.transaction():
            self._record_order(
                account_id, order_id, agent_id, symbol,
                market_type.value, side.value, quantity,
            )

            if market_type == MarketType.SPOT:
                if side == Side.BUY:
                    fill_price, fee, asset = self._spot_buy(
                        account_id, agent_id, symbol,
                        quantity, price, order_id,
                    )
                else:
                    fill_price, fee, asset, realized = self._spot_sell(
                        account_id, agent_id, symbol,
                        quantity, price, order_id,
                    )
            else:
                if side == Side.SELL:
                    raise ValueError(
                        "Use open_futures_position(direction='SHORT') "
                        "for opening short positions"
                    )
                fill_price = calculate_fill_price(
                    price, "BUY", self.slippage_rate
                )
                fee = calculate_fee(
                    fill_price, quantity, self.fee_rate
                )
                margin = calculate_initial_margin(
                    fill_price, quantity, leverage
                )
                if self._cash(account_id) < margin + fee:
                    raise ValueError("Insufficient DEMO cash for margin and fee")

                position_id = uuid4().hex
                self._open_futures(
                    account_id, agent_id, symbol, "LONG",
                    quantity, fill_price, leverage, margin,
                    fee, position_id, order_id,
                )

            slippage = abs(fill_price - price) * quantity
            fill_id = self._record_fill(
                order_id, fill_price, quantity, fee,
                "USDT", slippage,
            )

        return {
            "order_id": order_id,
            "fill_id": fill_id,
            "status": "FILLED",
            "symbol": symbol,
            "market_type": market_type.value,
            "side": side.value,
            "quantity": quantity,
            "execution_price": fill_price,
            "fee": fee,
            "realized_pnl": realized,
        }

    def _open_futures(
        self, account_id, agent_id, symbol, direction,
        quantity, price, leverage, margin, fee,
        position_id, reference,
    ):
        self._post(
            account_id, "MARGIN_LOCK", f"{reference}:margin",
            [
                ("MARGIN_LOCKED", "USDT", margin, "0", "ASSET"),
                ("CASH", "USDT", "0", margin, "ASSET"),
            ],
        )
        if fee > 0:
            self._post(
                account_id, "TRADING_FEE", f"{reference}:fee",
                [
                    ("TRADING_FEES", "USDT", fee, "0", "EXPENSE"),
                    ("CASH", "USDT", "0", fee, "ASSET"),
                ],
            )

        self.connection.execute(
            """
            INSERT INTO positions
                (position_id, account_id, agent_id, symbol, market_type,
                 direction, initial_quantity, remaining_quantity,
                 average_entry_price, leverage, status)
            VALUES (?, ?, ?, ?, 'FUTURES', ?, ?, ?, ?, ?, 'OPEN')
            """,
            (
                position_id, account_id, agent_id, symbol, direction,
                str(quantity), str(quantity), str(price), str(leverage),
            ),
        )
        self.connection.execute(
            """
            INSERT INTO margin_reservations
                (reservation_id, position_id, amount)
            VALUES (?, ?, ?)
            """,
            (uuid4().hex, position_id, str(margin)),
        )
        self.connection.execute(
            """
            INSERT INTO position_events
                (event_id, position_id, event_type, quantity,
                 execution_price, fee_amount, reference_id)
            VALUES (?, ?, 'OPEN', ?, ?, ?, ?)
            """,
            (
                uuid4().hex, position_id, str(quantity),
                str(price), str(fee), reference,
            ),
        )

    def open_futures_position(
        self,
        account_id,
        *,
        agent_id,
        symbol,
        direction,
        quantity,
        market_price,
        leverage=Decimal("1"),
        reference_id=None,
    ):
        self._account(account_id)
        symbol = str(symbol).upper().strip()
        self._asset(symbol)
        direction = str(direction).upper()
        if direction not in ("LONG", "SHORT"):
            raise ValueError("direction must be LONG or SHORT")

        quantity = self._decimal(quantity, "quantity", positive=True)
        price = self._decimal(market_price, "market_price", positive=True)
        leverage = self._decimal(leverage, "leverage", positive=True)
        reference_id = reference_id or uuid4().hex
        side = "BUY" if direction == "LONG" else "SELL"
        fill_price = calculate_fill_price(
            price, side, self.slippage_rate
        )
        margin = calculate_initial_margin(
            fill_price, quantity, leverage
        )
        fee = calculate_fee(fill_price, quantity, self.fee_rate)
        position_id = uuid4().hex

        with self.database.transaction():
            if self._cash(account_id) < margin + fee:
                raise ValueError("Insufficient DEMO cash for margin and fee")

            self._open_futures(
                account_id, agent_id, symbol, direction,
                quantity, fill_price, leverage, margin, fee,
                position_id, reference_id,
            )

        return {
            "position_id": position_id,
            "direction": direction,
            "quantity": quantity,
            "entry_price": fill_price,
            "initial_margin": margin,
            "fee": fee,
            "status": "OPEN",
        }

    def close_futures_position(
        self,
        account_id,
        position_id,
        *,
        market_price,
        quantity=None,
        reason="CLOSE",
    ):
        self._account(account_id)
        price = self._decimal(market_price, "market_price", positive=True)

        with self.database.transaction():
            position = self.connection.execute(
                """
                SELECT * FROM positions
                WHERE position_id = ? AND account_id = ?
                  AND market_type = 'FUTURES'
                  AND status IN ('OPEN', 'PARTIALLY_CLOSED')
                """,
                (position_id, account_id),
            ).fetchone()

            if position is None:
                raise ValueError("Open futures position not found")

            remaining = Decimal(position["remaining_quantity"])
            close_qty = (
                remaining if quantity is None
                else self._decimal(quantity, "quantity", positive=True)
            )
            if close_qty > remaining:
                raise ValueError("Close quantity exceeds open quantity")

            direction = position["direction"]
            exit_side = "SELL" if direction == "LONG" else "BUY"
            fill_price = calculate_fill_price(
                price, exit_side, self.slippage_rate
            )
            entry_price = Decimal(position["average_entry_price"])
            leverage = Decimal(position["leverage"])
            initial_qty = Decimal(position["initial_quantity"])

            pnl = calculate_futures_pnl(
                entry_price, fill_price, close_qty, direction
            )
            fee = calculate_fee(fill_price, close_qty, self.fee_rate)

            reservations = self.connection.execute(
                """
                SELECT reservation_id, amount, released_amount
                FROM margin_reservations
                WHERE position_id = ? AND status != 'RELEASED'
                """,
                (position_id,),
            ).fetchall()

            total_locked = sum(
                (
                    Decimal(row["amount"]) - Decimal(row["released_amount"])
                    for row in reservations
                ),
                Decimal("0"),
            )
            release = total_locked * close_qty / remaining
            new_remaining = remaining - close_qty

            if release > 0:
                self._post(
                    account_id, "MARGIN_RELEASE",
                    f"{position_id}:{uuid4().hex}:margin",
                    [
                        ("CASH", "USDT", release, "0", "ASSET"),
                        ("MARGIN_LOCKED", "USDT", "0", release, "ASSET"),
                    ],
                )

            if pnl > 0:
                pnl_lines = [
                    ("CASH", "USDT", pnl, "0", "ASSET"),
                    ("FUTURES_PNL", "USDT", "0", pnl, "INCOME"),
                ]
            elif pnl < 0:
                loss = abs(pnl)
                pnl_lines = [
                    ("FUTURES_PNL", "USDT", loss, "0", "EXPENSE"),
                    ("CASH", "USDT", "0", loss, "ASSET"),
                ]
            else:
                pnl_lines = []

            if pnl_lines:
                self._post(
                    account_id, "FUTURES_REALIZED_PNL",
                    f"{position_id}:{uuid4().hex}:pnl",
                    pnl_lines,
                )

            if fee > 0:
                self._post(
                    account_id, "TRADING_FEE",
                    f"{position_id}:{uuid4().hex}:fee",
                    [
                        ("TRADING_FEES", "USDT", fee, "0", "EXPENSE"),
                        ("CASH", "USDT", "0", fee, "ASSET"),
                    ],
                )

            for reservation in reservations:
                old_released = Decimal(reservation["released_amount"])
                old_amount = Decimal(reservation["amount"])
                allocated = old_amount - old_released
                if allocated <= 0:
                    continue
                part = (
                    allocated if new_remaining == 0
                    else allocated * close_qty / remaining
                )
                updated = old_released + part
                status = (
                    "RELEASED" if updated >= old_amount
                    else "PARTIALLY_RELEASED"
                )
                self.connection.execute(
                    """
                    UPDATE margin_reservations
                    SET released_amount = ?, status = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE reservation_id = ?
                    """,
                    (str(updated), status, reservation["reservation_id"]),
                )

            status = "CLOSED" if new_remaining == 0 else "PARTIALLY_CLOSED"
            self.connection.execute(
                """
                UPDATE positions
                SET remaining_quantity = ?, status = ?,
                    closed_at = CASE WHEN ? = 'CLOSED'
                                     THEN CURRENT_TIMESTAMP ELSE closed_at END
                WHERE position_id = ?
                """,
                (str(new_remaining), status, status, position_id),
            )

            self.connection.execute(
                """
                INSERT INTO position_events
                    (event_id, position_id, event_type, quantity,
                     execution_price, realized_pnl, fee_amount, reference_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid4().hex, position_id,
                    reason if reason in (
                        "CLOSE", "PARTIAL_CLOSE", "STOP_LOSS",
                        "TAKE_PROFIT", "LIQUIDATION"
                    ) else ("CLOSE" if new_remaining == 0 else "PARTIAL_CLOSE"),
                    str(close_qty), str(fill_price), str(pnl),
                    str(fee), uuid4().hex,
                ),
            )

        return {
            "position_id": position_id,
            "status": status,
            "closed_quantity": close_qty,
            "remaining_quantity": new_remaining,
            "execution_price": fill_price,
            "realized_pnl": pnl,
            "fee": fee,
            "margin_released": release,
        }

    def update_mark_price(self, symbol, market_type, price, source="BINANCE"):
        symbol = str(symbol).upper().strip()
        market_type = (
            market_type.value if isinstance(market_type, MarketType)
            else str(market_type).upper()
        )
        price = self._decimal(price, "price", positive=True)

        from datetime import datetime, timezone
        timestamp = datetime.now(timezone.utc).isoformat()

        with self.database.transaction():
            self.connection.execute(
                """
                INSERT INTO market_marks
                    (symbol, market_type, price, source, source_timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (symbol, market_type, str(price), source, timestamp),
            )

        return {
            "symbol": symbol,
            "market_type": market_type,
            "price": price,
            "source": source,
            "timestamp": timestamp,
        }

    def get_open_positions(self, account_id, agent_id=None):
        if agent_id is None:
            rows = self.connection.execute(
                """
                SELECT * FROM positions
                WHERE account_id = ? AND status IN ('OPEN', 'PARTIALLY_CLOSED')
                ORDER BY opened_at
                """,
                (account_id,),
            ).fetchall()
        else:
            rows = self.connection.execute(
                """
                SELECT * FROM positions
                WHERE account_id = ? AND agent_id = ?
                  AND status IN ('OPEN', 'PARTIALLY_CLOSED')
                ORDER BY opened_at
                """,
                (account_id, agent_id),
            ).fetchall()

        return [dict(row) for row in rows]

    def get_account_summary(self, account_id):
        self._account(account_id)
        cash = self._cash(account_id)

        # Aggregate inventory across all agents without losing quantities.
        inventory_rows = self.connection.execute(
            """
            SELECT asset_code,
                   SUM(CAST(quantity AS REAL)) AS total_quantity
            FROM spot_inventory
            WHERE account_id = ?
            GROUP BY asset_code
            """,
            (account_id,),
        ).fetchall()

        inventory = {}
        spot_inventory_value = Decimal("0")
        unpriced_spot_assets = []

        for row in inventory_rows:
            asset = row["asset_code"]
            agent_rows = self.connection.execute(
                """
                SELECT quantity, average_cost
                FROM spot_inventory
                WHERE account_id = ? AND asset_code = ?
                """,
                (account_id, asset),
            ).fetchall()

            quantity = sum(
                (Decimal(r["quantity"]) for r in agent_rows),
                Decimal("0"),
            )
            cost_basis = sum(
                (
                    Decimal(r["quantity"]) * Decimal(r["average_cost"])
                    for r in agent_rows
                ),
                Decimal("0"),
            )
            average_cost = (
                cost_basis / quantity if quantity else Decimal("0")
            )

            mark = self.connection.execute(
                """
                SELECT price, source_timestamp
                FROM market_marks
                WHERE symbol = ? AND market_type = 'SPOT'
                ORDER BY source_timestamp DESC, id DESC
                LIMIT 1
                """,
                (asset + "USDT",),
            ).fetchone()

            market_price = (
                Decimal(mark["price"]) if mark else average_cost
            )
            market_value = quantity * market_price
            spot_inventory_value += market_value

            if mark is None:
                unpriced_spot_assets.append(asset)

            inventory[asset] = {
                "quantity": quantity,
                "average_cost": average_cost,
                "market_price": market_price,
                "market_value": market_value,
                "price_timestamp": mark["source_timestamp"] if mark else None,
                "valuation_source": "MARKET" if mark else "COST_BASIS",
            }

        # Active futures margin.
        locked_rows = self.connection.execute(
            """
            SELECT mr.amount, mr.released_amount
            FROM margin_reservations mr
            JOIN positions p ON p.position_id = mr.position_id
            WHERE p.account_id = ?
              AND p.status IN ('OPEN', 'PARTIALLY_CLOSED')
              AND mr.status != 'RELEASED'
            """,
            (account_id,),
        ).fetchall()

        locked_margin = sum(
            (
                Decimal(r["amount"]) - Decimal(r["released_amount"])
                for r in locked_rows
            ),
            Decimal("0"),
        )

        # Unrealized futures PnL from the latest recorded market marks.
        positions = self.connection.execute(
            """
            SELECT position_id, symbol, direction,
                   remaining_quantity, average_entry_price
            FROM positions
            WHERE account_id = ?
              AND market_type = 'FUTURES'
              AND status IN ('OPEN', 'PARTIALLY_CLOSED')
            """,
            (account_id,),
        ).fetchall()

        unrealized_pnl = Decimal("0")
        unpriced_positions = []

        for position in positions:
            mark = self.connection.execute(
                """
                SELECT price
                FROM market_marks
                WHERE symbol = ? AND market_type = 'FUTURES'
                ORDER BY source_timestamp DESC, id DESC
                LIMIT 1
                """,
                (position["symbol"],),
            ).fetchone()

            if mark is None:
                unpriced_positions.append(position["position_id"])
                continue

            quantity = Decimal(position["remaining_quantity"])
            entry = Decimal(position["average_entry_price"])
            market = Decimal(mark["price"])

            if position["direction"] == "LONG":
                unrealized_pnl += (market - entry) * quantity
            else:
                unrealized_pnl += (entry - market) * quantity

        # Realized futures PnL from position events using exact Decimal arithmetic.
        futures_realized_rows = self.connection.execute(
            """
            SELECT pe.realized_pnl
            FROM position_events pe
            JOIN positions p ON p.position_id = pe.position_id
            WHERE p.account_id = ? AND p.market_type = 'FUTURES'
            """,
            (account_id,),
        ).fetchall()
        futures_realized = sum(
            (Decimal(row["realized_pnl"] or "0") for row in futures_realized_rows),
            Decimal("0"),
        )

        # Realized spot PnL from posted ledger entries using exact Decimal arithmetic.
        spot_realized_rows = self.connection.execute(
            """
            SELECT jl.credit, jl.debit
            FROM journal_lines jl
            JOIN journal_entries je ON je.id = jl.entry_id
            JOIN ledger_accounts la ON la.id = jl.ledger_account_id
            WHERE je.account_id = ?
              AND je.status = 'POSTED'
              AND la.account_code = 'SPOT_REALIZED_PNL'
              AND jl.asset_code = 'USDT'
            """,
            (account_id,),
        ).fetchall()
        spot_realized = sum(
            (
                Decimal(row["credit"] or "0") - Decimal(row["debit"] or "0")
                for row in spot_realized_rows
            ),
            Decimal("0"),
        )

        futures_fees = sum(
            (
                Decimal(row["fee_amount"])
                for row in self.connection.execute(
                    """
                    SELECT pe.fee_amount
                    FROM position_events pe
                    JOIN positions p ON p.position_id = pe.position_id
                    WHERE p.account_id = ? AND p.market_type = 'FUTURES'
                    """,
                    (account_id,),
                ).fetchall()
            ),
            Decimal("0"),
        )

        spot_fees = sum(
            (
                Decimal(row["fee_amount"])
                for row in self.connection.execute(
                    """
                    SELECT f.fee_amount
                    FROM fills f
                    JOIN orders o ON o.order_id = f.order_id
                    WHERE o.account_id = ? AND f.fee_asset = 'USDT'
                    """,
                    (account_id,),
                ).fetchall()
            ),
            Decimal("0"),
        )
        total_fees = futures_fees + spot_fees

        realized_pnl = futures_realized + spot_realized
        wallet_balance = cash + locked_margin
        equity = (
            wallet_balance
            + spot_inventory_value
            + unrealized_pnl
        )

        return {
            "account_id": account_id,
            "wallet_balance": wallet_balance,
            "available_balance": cash,
            "locked_margin": locked_margin,
            "spot_inventory": inventory,
            "spot_inventory_value": spot_inventory_value,
            "unrealized_pnl": unrealized_pnl,
            "realized_pnl": realized_pnl,
            "total_fees": total_fees,
            "net_realized_pnl": realized_pnl - total_fees,
            "equity": equity,
            "unpriced_spot_assets": unpriced_spot_assets,
            "unpriced_positions": unpriced_positions,
        }
