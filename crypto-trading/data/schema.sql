PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS source (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    import_method TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS candle (
    source_id TEXT NOT NULL REFERENCES source(id),
    pair TEXT NOT NULL,
    interval_min INTEGER NOT NULL CHECK (interval_min > 0),
    opened_at INTEGER NOT NULL,
    closed_at INTEGER NOT NULL,
    open REAL NOT NULL CHECK (open > 0),
    high REAL NOT NULL CHECK (high >= max(open, close)),
    low REAL NOT NULL CHECK (low > 0 AND low <= min(open, close)),
    close REAL NOT NULL CHECK (close > 0),
    base_volume REAL NOT NULL CHECK (base_volume >= 0),
    reference TEXT NOT NULL,
    imported_at INTEGER NOT NULL,
    PRIMARY KEY (source_id, pair, interval_min, opened_at),
    CHECK (closed_at = opened_at + interval_min * 60)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS reference_price (
    source_id TEXT NOT NULL REFERENCES source(id),
    pair TEXT NOT NULL,
    reference_date TEXT NOT NULL,
    price REAL NOT NULL CHECK (price > 0),
    imported_at INTEGER NOT NULL,
    PRIMARY KEY (source_id, pair, reference_date)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS event (
    source_id TEXT NOT NULL REFERENCES source(id),
    external_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    entity TEXT NOT NULL,
    occurred_at INTEGER,
    published_at INTEGER,
    available_at INTEGER NOT NULL,
    observed_at INTEGER NOT NULL,
    confidence TEXT NOT NULL CHECK (confidence IN ('official','reported','rumor')),
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    PRIMARY KEY (source_id, external_id, available_at),
    CHECK (published_at IS NULL OR available_at >= published_at)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS event_by_time ON event(available_at);
CREATE TABLE IF NOT EXISTS imported_archive (
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    first_at INTEGER NOT NULL,
    last_at INTEGER NOT NULL,
    row_count INTEGER NOT NULL,
    imported_at INTEGER NOT NULL,
    PRIMARY KEY (filename, sha256)
) WITHOUT ROWID;
CREATE VIEW IF NOT EXISTS coverage AS
SELECT source_id, pair, interval_min, count(*) AS candle_count,
       date(min(opened_at), 'unixepoch') AS first_date,
       date(max(opened_at), 'unixepoch') AS last_date,
       (max(opened_at)-min(opened_at))/(interval_min*60)+1-count(*) AS missing_slots
FROM candle GROUP BY source_id, pair, interval_min;
