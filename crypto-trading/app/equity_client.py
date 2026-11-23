"""Dnevni podaci za glavne američke dioničke indekse ('Wall Street') i cijenu zlata, radi testiranja
koristi li makro trend (risk-on/risk-off, "safe haven" potražnja za zlatom) kao filter za kripto
strategije.

NAPOMENA O POUZDANOSTI (isti princip kao kod TED/EOJN/Coinbase providera): izvor je Stooq-ov javni
CSV izvoz (stooq.com/q/d/l/), koji ne treba API ključ. Endpoint i simboli (^spx, ^dji, ^ndq, xauusd)
su napisani prema poznatoj javnoj upotrebi Stooq-a u trenutku pisanja koda, ali NISU uživo testirani
jer ovo razvojno okruženje nema izlazni pristup internetu. Pokreni "Testiraj vezu" na dashboardu
(odjeljak Wall Street) iz okoline s internet pristupom prije nego se osloniš na ovaj podatak -
popravak simbola/formata je izoliran u ovoj datoteci.
"""
import calendar
import csv
import io
import time

import httpx

from app.candles import Candle

STOOQ_BASE = "https://stooq.com/q/d/l/"

# Oznaka -> Stooq simbol. Dopuni/ispravi ovdje ako "Testiraj vezu" pokaže da simbol ne postoji.
INDEX_SYMBOLS = {
    "SPX": "^spx",  # S&P 500
    "DJI": "^dji",  # Dow Jones Industrial Average
    "NDQ": "^ndq",  # Nasdaq Composite
    "GOLD": "xauusd",  # Zlato, spot USD/unca
}


class EquityError(Exception):
    pass


def _fetch_csv(stooq_symbol: str) -> list[dict]:
    with httpx.Client(timeout=15) as client:
        resp = client.get(STOOQ_BASE, params={"s": stooq_symbol, "i": "d"})
    if resp.status_code != 200:
        raise EquityError(f"HTTP {resp.status_code} od Stooqa za {stooq_symbol}: {resp.text[:300]}")
    text = resp.text.strip()
    if not text or text.lower().startswith("<!doctype") or "," not in text.splitlines()[0]:
        raise EquityError(f"Neočekivan odgovor Stooqa za {stooq_symbol} (nije CSV): {text[:200]}")
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise EquityError(f"Stooq je vratio prazan CSV za {stooq_symbol} - provjeri je li simbol točan.")
    return rows


def fetch_recent_candles(label: str, days: int = 200) -> list[Candle]:
    """Za paper/live engine - zadnjih `days` zatvorenih dnevnih svijeća, bez diranja baze."""
    symbol = INDEX_SYMBOLS.get(label, label)
    rows = _fetch_csv(symbol)
    cutoff = time.time() - days * 86400
    candles = []
    for row in rows:
        try:
            opened_at = calendar.timegm(time.strptime(row["Date"], "%Y-%m-%d"))
        except (KeyError, ValueError) as err:
            raise EquityError(f"Neočekivan format retka u Stooq CSV-u: {row} ({err})")
        if opened_at < cutoff:
            continue
        candles.append(
            Candle(
                opened_at=opened_at,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row.get("Volume") or 0),
            )
        )
    candles.sort(key=lambda c: c.opened_at)
    return candles


def sync_to_db(conn, label: str) -> int:
    """Povlači cijelu dostupnu povijest i sprema u candle tablicu (source_id='stooq', pair=label,
    interval_min=1440), radi korištenja u backtestu. Vraća broj upisanih/ažuriranih redaka."""
    symbol = INDEX_SYMBOLS.get(label, label)
    rows = _fetch_csv(symbol)

    conn.execute(
        "INSERT OR IGNORE INTO source VALUES (?, ?, ?, ?, ?)",
        ("stooq", "equity_index", "Stooq (Wall Street indeksi)", "https://stooq.com", "CSV izvoz"),
    )

    now = int(time.time())
    count = 0
    for row in rows:
        try:
            opened_at = calendar.timegm(time.strptime(row["Date"], "%Y-%m-%d"))
            open_, high, low, close = (float(row[k]) for k in ("Open", "High", "Low", "Close"))
            volume = float(row.get("Volume") or 0)
        except (KeyError, ValueError):
            continue
        conn.execute(
            """INSERT INTO candle VALUES ('stooq', ?, 1440, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (source_id, pair, interval_min, opened_at) DO UPDATE SET
                 open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close,
                 base_volume=excluded.base_volume, imported_at=excluded.imported_at
               WHERE candle.close != excluded.close""",
            (label, opened_at, opened_at + 86400, open_, high, low, close, volume, STOOQ_BASE, now),
        )
        count += 1
    conn.commit()
    return count


def test_connection() -> dict:
    result = {}
    for label in INDEX_SYMBOLS:
        try:
            candles = fetch_recent_candles(label, days=10)
            result[label] = {"ok": True, "message": f"{len(candles)} svijeća, zadnja: {candles[-1].close if candles else '?'}"}
        except Exception as err:
            result[label] = {"ok": False, "message": str(err)}
    return result
