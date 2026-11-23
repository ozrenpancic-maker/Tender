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
    mode TEXT NOT NULL DEFAULT 'paper', -- uvijek 'paper' - aplikacija je savjetnik/simulator, nikad ne šalje prave naloge
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

-- Jedna vrijednost po danu (ne OHLC) - za FRED makro serije, DeFiLlama TVL, CoinGecko ponudu
-- tokena, Google Trends interes, Reddit/regulatorni sentiment skor itd.
CREATE TABLE IF NOT EXISTS macro_series (
    source TEXT NOT NULL, -- fred | defillama | coingecko | google_trends | reddit | etf_flow | regulatory
    series_id TEXT NOT NULL, -- npr. 'FEDFUNDS', 'ethereum' (TVL chain), 'bitcoin' (coingecko id)
    observed_date TEXT NOT NULL, -- YYYY-MM-DD (UTC) - dan NA KOJI se podatak odnosi
    available_date TEXT NOT NULL DEFAULT '', -- YYYY-MM-DD - dan kad je podatak STVARNO bio dostupan
    value REAL NOT NULL,
    imported_at INTEGER NOT NULL,
    PRIMARY KEY (source, series_id, observed_date)
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
