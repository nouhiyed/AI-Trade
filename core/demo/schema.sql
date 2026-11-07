PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS demo_accounts (
    account_id TEXT PRIMARY KEY,
    initial_capital TEXT NOT NULL,
    quote_asset TEXT NOT NULL DEFAULT 'USDT',
    status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'SUSPENDED', 'CLOSED')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ledger_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    account_code TEXT NOT NULL,
    account_name TEXT NOT NULL,
    account_type TEXT NOT NULL
        CHECK (account_type IN ('ASSET', 'LIABILITY', 'EQUITY', 'INCOME', 'EXPENSE')),
    asset_code TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES demo_accounts(account_id),
    UNIQUE (account_id, account_code, asset_code)
);

CREATE TABLE IF NOT EXISTS journal_entries (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    reference_id TEXT,
    idempotency_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT', 'POSTED')),
    description TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    posted_at TEXT,
    FOREIGN KEY (account_id) REFERENCES demo_accounts(account_id)
);

CREATE TABLE IF NOT EXISTS journal_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id TEXT NOT NULL,
    ledger_account_id INTEGER NOT NULL,
    asset_code TEXT NOT NULL,
    debit TEXT NOT NULL DEFAULT '0',
    credit TEXT NOT NULL DEFAULT '0',
    FOREIGN KEY (entry_id) REFERENCES journal_entries(id),
    FOREIGN KEY (ledger_account_id) REFERENCES ledger_accounts(id),
    CHECK (
        (debit <> '0' AND credit = '0')
        OR
        (credit <> '0' AND debit = '0')
    )
);

CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    market_type TEXT NOT NULL
        CHECK (market_type IN ('SPOT', 'FUTURES', 'ALPHA')),
    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    order_type TEXT NOT NULL
        CHECK (order_type IN ('MARKET', 'LIMIT')),
    quantity TEXT NOT NULL,
    limit_price TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN (
            'PENDING', 'PARTIALLY_FILLED', 'FILLED',
            'CANCELLED', 'REJECTED'
        )),
    filled_quantity TEXT NOT NULL DEFAULT '0',
    average_fill_price TEXT NOT NULL DEFAULT '0',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES demo_accounts(account_id)
);

CREATE TABLE IF NOT EXISTS fills (
    fill_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    execution_price TEXT NOT NULL,
    quantity TEXT NOT NULL,
    fee_amount TEXT NOT NULL DEFAULT '0',
    fee_asset TEXT NOT NULL,
    slippage_amount TEXT NOT NULL DEFAULT '0',
    executed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

CREATE TABLE IF NOT EXISTS positions (
    position_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    market_type TEXT NOT NULL
        CHECK (market_type IN ('SPOT', 'FUTURES', 'ALPHA')),
    direction TEXT NOT NULL
        CHECK (direction IN ('LONG', 'SHORT')),
    initial_quantity TEXT NOT NULL,
    remaining_quantity TEXT NOT NULL,
    average_entry_price TEXT NOT NULL,
    leverage TEXT NOT NULL DEFAULT '1',
    status TEXT NOT NULL DEFAULT 'OPEN'
        CHECK (status IN ('OPEN', 'PARTIALLY_CLOSED', 'CLOSED')),
    opened_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at TEXT,
    FOREIGN KEY (account_id) REFERENCES demo_accounts(account_id)
);

CREATE TABLE IF NOT EXISTS position_events (
    event_id TEXT PRIMARY KEY,
    position_id TEXT NOT NULL,
    event_type TEXT NOT NULL
        CHECK (event_type IN (
            'OPEN', 'ADD', 'PARTIAL_CLOSE', 'CLOSE',
            'STOP_LOSS', 'TAKE_PROFIT', 'LIQUIDATION'
        )),
    quantity TEXT NOT NULL,
    execution_price TEXT NOT NULL,
    realized_pnl TEXT NOT NULL DEFAULT '0',
    fee_amount TEXT NOT NULL DEFAULT '0',
    reference_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (position_id) REFERENCES positions(position_id)
);

CREATE TABLE IF NOT EXISTS spot_inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    asset_code TEXT NOT NULL,
    quantity TEXT NOT NULL,
    average_cost TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES demo_accounts(account_id),
    UNIQUE (account_id, agent_id, asset_code)
);

CREATE TABLE IF NOT EXISTS margin_reservations (
    reservation_id TEXT PRIMARY KEY,
    position_id TEXT NOT NULL,
    amount TEXT NOT NULL,
    released_amount TEXT NOT NULL DEFAULT '0',
    status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'PARTIALLY_RELEASED', 'RELEASED')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (position_id) REFERENCES positions(position_id)
);

CREATE TABLE IF NOT EXISTS funding_payments (
    payment_id TEXT PRIMARY KEY,
    position_id TEXT NOT NULL,
    amount TEXT NOT NULL,
    asset_code TEXT NOT NULL,
    payment_time TEXT NOT NULL,
    reference_id TEXT NOT NULL UNIQUE,
    FOREIGN KEY (position_id) REFERENCES positions(position_id)
);

CREATE TABLE IF NOT EXISTS market_marks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    market_type TEXT NOT NULL,
    price TEXT NOT NULL,
    source TEXT NOT NULL,
    source_timestamp TEXT NOT NULL,
    received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (symbol, market_type, source, source_timestamp)
);

CREATE TABLE IF NOT EXISTS demo_events (
    event_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    aggregate_type TEXT,
    aggregate_id TEXT,
    payload_json TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES demo_accounts(account_id)
);

CREATE INDEX IF NOT EXISTS idx_journal_account
    ON journal_entries(account_id, created_at);

CREATE INDEX IF NOT EXISTS idx_journal_lines_entry
    ON journal_lines(entry_id);

CREATE INDEX IF NOT EXISTS idx_orders_account_status
    ON orders(account_id, status, created_at);

CREATE INDEX IF NOT EXISTS idx_fills_order
    ON fills(order_id, executed_at);

CREATE INDEX IF NOT EXISTS idx_positions_account_status
    ON positions(account_id, status);

CREATE INDEX IF NOT EXISTS idx_positions_agent
    ON positions(agent_id, status);

CREATE INDEX IF NOT EXISTS idx_position_events_position
    ON position_events(position_id, created_at);

CREATE INDEX IF NOT EXISTS idx_margin_position
    ON margin_reservations(position_id, status);

CREATE INDEX IF NOT EXISTS idx_funding_position
    ON funding_payments(position_id, payment_time);

CREATE INDEX IF NOT EXISTS idx_market_marks_lookup
    ON market_marks(symbol, market_type, source_timestamp);

CREATE INDEX IF NOT EXISTS idx_demo_events_account
    ON demo_events(account_id, created_at);

CREATE TRIGGER IF NOT EXISTS trg_journal_line_account_match
BEFORE INSERT ON journal_lines
BEGIN
    SELECT CASE
        WHEN (
            SELECT account_id
            FROM journal_entries
            WHERE id = NEW.entry_id
        ) IS NULL
        THEN RAISE(ABORT, 'Journal entry does not exist')
    END;

    SELECT CASE
        WHEN (
            SELECT account_id
            FROM journal_entries
            WHERE id = NEW.entry_id
        ) <> (
            SELECT account_id
            FROM ledger_accounts
            WHERE id = NEW.ledger_account_id
        )
        THEN RAISE(ABORT, 'Ledger account belongs to another account')
    END;

    SELECT CASE
        WHEN (
            SELECT asset_code
            FROM ledger_accounts
            WHERE id = NEW.ledger_account_id
        ) <> NEW.asset_code
        THEN RAISE(ABORT, 'Asset code mismatch')
    END;

    SELECT CASE
        WHEN (
            SELECT status
            FROM journal_entries
            WHERE id = NEW.entry_id
        ) <> 'DRAFT'
        THEN RAISE(ABORT, 'Cannot modify a posted journal entry')
    END;
END;

CREATE TRIGGER IF NOT EXISTS trg_journal_line_update_account_match
BEFORE UPDATE OF entry_id, ledger_account_id, asset_code ON journal_lines
BEGIN
    SELECT CASE
        WHEN (SELECT status FROM journal_entries WHERE id = NEW.entry_id) IS NULL
        THEN RAISE(ABORT, 'Journal entry does not exist')
    END;

    SELECT CASE
        WHEN (SELECT status FROM journal_entries WHERE id = NEW.entry_id) <> 'DRAFT'
        THEN RAISE(ABORT, 'Cannot modify a posted journal entry')
    END;

    SELECT CASE
        WHEN (SELECT account_id FROM journal_entries WHERE id = NEW.entry_id)
          <> (SELECT account_id FROM ledger_accounts WHERE id = NEW.ledger_account_id)
        THEN RAISE(ABORT, 'Ledger account belongs to another account')
    END;

    SELECT CASE
        WHEN (SELECT asset_code FROM ledger_accounts WHERE id = NEW.ledger_account_id)
          <> NEW.asset_code
        THEN RAISE(ABORT, 'Asset code mismatch')
    END;
END;

CREATE TRIGGER IF NOT EXISTS trg_journal_decimal_line_valid
BEFORE INSERT ON journal_lines
BEGIN
    SELECT CASE
        WHEN demo_decimal_line_valid(NEW.debit, NEW.credit) <> 1
        THEN RAISE(ABORT, 'Invalid journal line amounts')
    END;
END;

CREATE TRIGGER IF NOT EXISTS trg_journal_decimal_line_update_valid
BEFORE UPDATE OF debit, credit ON journal_lines
BEGIN
    SELECT CASE
        WHEN demo_decimal_line_valid(NEW.debit, NEW.credit) <> 1
        THEN RAISE(ABORT, 'Invalid journal line amounts')
    END;
END;

CREATE TRIGGER IF NOT EXISTS trg_journal_entry_balance_before_post
BEFORE UPDATE OF status ON journal_entries
WHEN OLD.status = 'DRAFT' AND NEW.status = 'POSTED'
BEGIN
    SELECT CASE
        WHEN (
            SELECT COUNT(*)
            FROM journal_lines
            WHERE entry_id = NEW.id
        ) < 2
        THEN RAISE(ABORT, 'Journal entry requires at least two lines')
    END;

    SELECT CASE
        WHEN EXISTS (
            SELECT asset_code
            FROM journal_lines
            WHERE entry_id = NEW.id
            GROUP BY asset_code
            HAVING demo_decimal_equal(
                demo_decimal_sum(debit),
                demo_decimal_sum(credit)
            ) <> 1
        )
        THEN RAISE(ABORT, 'Journal entry is not balanced per asset')
    END;
END;

CREATE TRIGGER IF NOT EXISTS trg_posted_journal_immutable
BEFORE UPDATE ON journal_entries
WHEN OLD.status = 'POSTED'
BEGIN
    SELECT RAISE(ABORT, 'Posted journal entries are immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_posted_journal_no_delete
BEFORE DELETE ON journal_entries
WHEN OLD.status = 'POSTED'
BEGIN
    SELECT RAISE(ABORT, 'Posted journal entries cannot be deleted');
END;

CREATE TRIGGER IF NOT EXISTS trg_posted_lines_no_update
BEFORE UPDATE ON journal_lines
WHEN (
    SELECT status FROM journal_entries WHERE id = OLD.entry_id
) = 'POSTED'
BEGIN
    SELECT RAISE(ABORT, 'Posted journal lines are immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_posted_lines_no_delete
BEFORE DELETE ON journal_lines
WHEN (
    SELECT status FROM journal_entries WHERE id = OLD.entry_id
) = 'POSTED'
BEGIN
    SELECT RAISE(ABORT, 'Posted journal lines cannot be deleted');
END;

INSERT OR IGNORE INTO schema_migrations (version, description)
VALUES (1, 'Initial DEMO accounting and trading schema');

PRAGMA user_version = 1;
