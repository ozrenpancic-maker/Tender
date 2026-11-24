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

-- Automatizirani multi-coin PAPER trading (AI Prediction Engine sam bira koji coin, u okviru
-- ograničenog virtualnog budžeta) - vidi app/auto_trader.py. I OVO JE SIMULACIJA, bez pravog novca
-- (KriptoMVP 4.4 pravilo #2/#3) - "automatizirano" znači autonomna ODLUKA, ne pravi nalog.
CREATE TABLE IF NOT EXISTS auto_trader_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    horizon TEXT NOT NULL, -- '1h' ili '4h' - SAMO validirani horizonti (vidi app/ml/engine.py)
    universe_json TEXT NOT NULL, -- lista parova, npr. ["XRP/USDT", "SUI/USDT", ...]
    starting_balance_eur REAL NOT NULL,
    max_position_pct REAL NOT NULL, -- max udio budžeta u jednom coinu odjednom (npr. 0.2 = 20%)
    started_at INTEGER NOT NULL,
    stopped_at INTEGER,
    status TEXT NOT NULL DEFAULT 'running', -- running | stopped
    cash_eur REAL NOT NULL, -- preostala slobodna gotovina (pozicije se prate zasebno)
    last_tick_bucket INTEGER NOT NULL DEFAULT 0 -- zadnji obrađeni horizont-period (sprječava dvostruko trgovanje unutar istog sata/4h)
);

CREATE TABLE IF NOT EXISTS auto_trader_position (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES auto_trader_run(id),
    pair TEXT NOT NULL,
    quantity_base REAL NOT NULL,
    entry_price REAL NOT NULL,
    entry_eur REAL NOT NULL,
    opened_at INTEGER NOT NULL,
    closed_at INTEGER, -- NULL = otvorena pozicija
    exit_price REAL,
    exit_eur REAL
);

CREATE TABLE IF NOT EXISTS auto_trader_trade (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES auto_trader_run(id),
    pair TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    price REAL NOT NULL,
    amount_eur REAL NOT NULL,
    ai_score INTEGER,
    decision TEXT, -- npr. 'STRONG BUY', 'SELL'
    executed_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS auto_trader_equity_point (
    run_id INTEGER NOT NULL REFERENCES auto_trader_run(id),
    at INTEGER NOT NULL,
    equity_eur REAL NOT NULL,
    cash_eur REAL NOT NULL,
    open_positions INTEGER NOT NULL,
    PRIMARY KEY (run_id, at)
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
