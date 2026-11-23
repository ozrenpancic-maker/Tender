-- Dodatne tablice iznad postojeće sheme (schema.sql) - ne diraju povijesne podatke.

CREATE TABLE IF NOT EXISTS paper_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy TEXT NOT NULL,
    params_json TEXT NOT NULL,
    pair TEXT NOT NULL,
    started_at INTEGER NOT NULL,
    stopped_at INTEGER,
    starting_balance_eur REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'running', -- running | stopped
    mode TEXT NOT NULL DEFAULT 'paper', -- paper | live
    last_evaluated_candle_at INTEGER
);

CREATE TABLE IF NOT EXISTS paper_trade (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES paper_run(id),
    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    price REAL NOT NULL,
    balance_after_eur REAL NOT NULL,
    position_after_base REAL NOT NULL,
    executed_at INTEGER NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS paper_equity_point (
    run_id INTEGER NOT NULL REFERENCES paper_run(id),
    at INTEGER NOT NULL,
    equity_eur REAL NOT NULL,
    price REAL NOT NULL,
    PRIMARY KEY (run_id, at)
);

CREATE TABLE IF NOT EXISTS live_order (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    pair TEXT NOT NULL,
    requested_eur REAL,
    coinbase_order_id TEXT,
    status TEXT NOT NULL,
    raw_response TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS backtest_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy TEXT NOT NULL,
    params_json TEXT NOT NULL,
    pair TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
