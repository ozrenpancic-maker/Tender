"""Generička pohrana/čitanje ne-OHLC (jedna vrijednost po danu) serija u macro_series tablici -
zajednička za FRED, DeFiLlama, CoinGecko, Google Trends, Reddit/regulatorni sentiment skor.

POINT-IN-TIME ISPRAVKA (nađeno u ChatGPT-ovoj neovisnoj reviziji): `observed_date` je dan NA KOJI
se podatak odnosi, ne dan kad je stvarno postao dostupan. Strategija koja gleda `observed_date`
izravno bi mogla "znati" vrijednost prije nego je objavljena (classic point-in-time leak).
`available_date` (= observed_date + LAG_DAYS po izvoru) pokušava to popraviti - `load_series`
sada filtrira/vraća po `available_date`, ne `observed_date`.

NAPOMENA O POUZDANOSTI LAG_DAYS: ovo su KONZERVATIVNE PROCJENE na temelju opće poznate prirode
svakog izvora (dnevni agregat se ne može znati prije kraja dana; makro statistika obično ima
barem 1-dnevni lag), NISU provjerene uživo protiv stvarnog kalendara objave svakog izvora (nema
pristupa internetu u ovom razvojnom okruženju). Prije nego im se ozbiljno vjeruje za live
trgovanje, provjeri stvarni kalendar objave svakog izvora (npr. FRED stranica serije obično
navodi "Release Dates")."""
import calendar
import time

LAG_DAYS = {
    "fred": 1,  # makro serije (npr. FEDFUNDS) - obično objavljeno sljedeći radni dan
    "defillama": 0,  # TVL se ažurira blizu uživo, ali dnevni agregat je stvarno gotov tek na kraju dana
    "coingecko": 0,  # tržišna kapitalizacija/opskrba - blizu uživo
    "google_trends": 2,  # Trends ima poznat kašnjenje izvještavanja od nekoliko dana
    "reddit": 1,  # dnevni sentiment skor - mora pokupiti cijeli dan prije agregacije
    "etf_flow": 1,  # tokovi prethodnog dana objavljeni sljedeći radni dan
    "regulatory": 1,  # dnevni skor iz RSS feedova - isto kao reddit, dan mora proći
}


def _add_days(date_str: str, days: int) -> str:
    ts = calendar.timegm(time.strptime(date_str, "%Y-%m-%d")) + days * 86400
    return time.strftime("%Y-%m-%d", time.gmtime(ts))


def load_series(conn, source: str, series_id: str, start_ts: int, end_ts: int) -> list[tuple[int, float]]:
    rows = conn.execute(
        "SELECT observed_date, available_date, value FROM macro_series WHERE source=? AND series_id=? ORDER BY observed_date",
        (source, series_id),
    ).fetchall()
    result = []
    for row in rows:
        available = row["available_date"] or row["observed_date"]
        ts = calendar.timegm(time.strptime(available, "%Y-%m-%d"))
        if start_ts <= ts <= end_ts:
            result.append((ts, row["value"]))
    return result


def save_series(conn, source: str, series_id: str, points: list[tuple[str, float]]) -> int:
    """points: [(YYYY-MM-DD, value), ...] - datum NA KOJI se vrijednost odnosi (observed_date).
    available_date se izvodi automatski (observed_date + LAG_DAYS[source])."""
    now = int(time.time())
    lag = LAG_DAYS.get(source, 1)  # nepoznat izvor - konzervativno pretpostavi barem 1 dan
    count = 0
    for date_str, value in points:
        available_date = _add_days(date_str, lag)
        conn.execute(
            """INSERT INTO macro_series (source, series_id, observed_date, available_date, value, imported_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT (source, series_id, observed_date) DO UPDATE SET
                 value=excluded.value, available_date=excluded.available_date, imported_at=excluded.imported_at
               WHERE macro_series.value != excluded.value""",
            (source, series_id, date_str, available_date, value, now),
        )
        count += 1
    conn.commit()
    return count
