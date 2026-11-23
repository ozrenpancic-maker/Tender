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


def resample_candles(candles: list[Candle], source_interval_min: int, target_interval_min: int) -> list[Candle]:
    """Agregira finije svijeće (npr. 5-min) u grublje (npr. 1h) - stvarna agregacija stvarnih
    podataka, ne izmišljeni podaci. `target_interval_min` mora biti višekratnik `source_interval_min`.
    Zadnja grupa se izbacuje ako nema sve očekivane pod-svijeće (nedovršen bucket)."""
    if target_interval_min % source_interval_min != 0:
        raise ValueError("target_interval_min mora biti višekratnik source_interval_min.")
    group_size = target_interval_min // source_interval_min
    bucket_seconds = target_interval_min * 60

    buckets: dict[int, list[Candle]] = {}
    for c in candles:
        bucket_start = (c.opened_at // bucket_seconds) * bucket_seconds
        buckets.setdefault(bucket_start, []).append(c)

    out = []
    for bucket_start in sorted(buckets):
        group = sorted(buckets[bucket_start], key=lambda c: c.opened_at)
        if len(group) < group_size:
            continue
        out.append(
            Candle(
                opened_at=bucket_start,
                open=group[0].open,
                high=max(g.high for g in group),
                low=min(g.low for g in group),
                close=group[-1].close,
                volume=sum(g.volume for g in group),
            )
        )
    return out
