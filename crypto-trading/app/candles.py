"""Čitanje povijesnih svijeća iz baze (izvor: Binance dnevne/5-min svijeće, vidi data/izvori.csv)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Candle:
    opened_at: int  # unix timestamp (UTC)
    open: float
    high: float
    low: float
    close: float
    volume: float


def load_candles(conn, source_id: str, pair: str, interval_min: int, start_ts: int, end_ts: int) -> list[Candle]:
    rows = conn.execute(
        """SELECT opened_at, open, high, low, close, base_volume FROM candle
           WHERE source_id=? AND pair=? AND interval_min=? AND opened_at BETWEEN ? AND ?
           ORDER BY opened_at""",
        (source_id, pair, interval_min, start_ts, end_ts),
    ).fetchall()
    return [Candle(r["opened_at"], r["open"], r["high"], r["low"], r["close"], r["base_volume"]) for r in rows]


def available_pairs(conn, source_id: str = "binance") -> list[str]:
    rows = conn.execute("SELECT DISTINCT pair FROM candle WHERE source_id=? ORDER BY pair", (source_id,)).fetchall()
    return [r["pair"] for r in rows]
