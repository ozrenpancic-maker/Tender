"""Generička pohrana/čitanje ne-OHLC (jedna vrijednost po danu) serija u macro_series tablici -
zajednička za FRED, DeFiLlama, CoinGecko, Google Trends, Reddit/regulatorni sentiment skor."""
import calendar
import time


def load_series(conn, source: str, series_id: str, start_ts: int, end_ts: int) -> list[tuple[int, float]]:
    rows = conn.execute(
        "SELECT observed_date, value FROM macro_series WHERE source=? AND series_id=? ORDER BY observed_date",
        (source, series_id),
    ).fetchall()
    result = []
    for row in rows:
        ts = calendar.timegm(time.strptime(row["observed_date"], "%Y-%m-%d"))
        if start_ts <= ts <= end_ts:
            result.append((ts, row["value"]))
    return result


def save_series(conn, source: str, series_id: str, points: list[tuple[str, float]]) -> int:
    """points: [(YYYY-MM-DD, value), ...]"""
    now = int(time.time())
    count = 0
    for date_str, value in points:
        conn.execute(
            """INSERT INTO macro_series VALUES (?, ?, ?, ?, ?)
               ON CONFLICT (source, series_id, observed_date) DO UPDATE SET
                 value=excluded.value, imported_at=excluded.imported_at
               WHERE macro_series.value != excluded.value""",
            (source, series_id, date_str, value, now),
        )
        count += 1
    conn.commit()
    return count
