"""Dnevna povijest cijena izravno preko Binance javnog REST API-ja (bez ključa) - za bilo koji par,
ne samo BTC/ETH/SOL koje je priloženi istraživački paket već imao. Sprema se u POSTOJEĆU `candle`
tablicu sa source_id='binance' - isti oblik kao povijesni podaci, pa odmah radi sa svim postojećim
strategijama/backtestom/optimizatorom bez ikakvih drugih promjena.

Za razliku od `app/kripto.py` (ZIP arhive, bulk povijesni import), ovo je jednostavan izravan REST
poziv prikladan za dodavanje pojedinačnih parova na zahtjev (npr. coinovi iz tvog stvarnog
portfelja koje izvorni paket nije pokrivao).

NAPOMENA O POUZDANOSTI: endpoint prema javnoj Binance REST API dokumentaciji, nije uživo testiran
u ovom okruženju (nema izlaznog pristupa internetu).
"""
import time

import httpx

from app.candles import Candle

BINANCE_API = "https://api.binance.com/api/v3/klines"

# Parovi iz korisnikovog stvarnog portfelja (vidi razgovor) -> Binance simbol.
# Namjerno izostavljene "dust" pozicije (SOL, ETH, AMP, JASMY ispod par centi) - trgovanje njima bi
# izgubilo više na naknadama nego što vrijedi sama pozicija.
PORTFOLIO_PAIRS = {
    "XRP/USDT": "XRPUSDT",
    "SUI/USDT": "SUIUSDT",
    "PEPE/USDT": "PEPEUSDT",
    "DOGE/USDT": "DOGEUSDT",
    "POL/USDT": "POLUSDT",  # Polygon rebrand MATIC->POL - provjeri "Testiraj vezu" ako ovo ne uspije
    "NEAR/USDT": "NEARUSDT",
    "ALGO/USDT": "ALGOUSDT",
}


class BinanceHistoryError(Exception):
    pass


def _symbol_for(pair: str) -> str:
    return PORTFOLIO_PAIRS.get(pair, pair.replace("/", ""))


def _fetch_page(symbol: str, start_ms: int, limit: int = 1000) -> list[list]:
    with httpx.Client(timeout=20) as client:
        resp = client.get(
            BINANCE_API,
            params={"symbol": symbol, "interval": "1d", "startTime": start_ms, "limit": limit},
        )
    if resp.status_code != 200:
        raise BinanceHistoryError(f"HTTP {resp.status_code} od Binance za {symbol}: {resp.text[:300]}")
    data = resp.json()
    if not isinstance(data, list):
        raise BinanceHistoryError(f"Neočekivan Binance odgovor za {symbol}: {str(data)[:300]}")
    return data


def _fetch_all_klines(symbol: str, since_ms: int) -> list[list]:
    rows: list[list] = []
    cursor = since_ms
    now_ms = int(time.time() * 1000)
    while cursor < now_ms:
        page = _fetch_page(symbol, cursor)
        if not page:
            break
        rows.extend(page)
        last_open_time = page[-1][0]
        if last_open_time <= cursor:
            break
        cursor = last_open_time + 86400_000  # dan nakon zadnje dohvaćene svijeće
        if len(page) < 1000:
            break
    return rows


def _to_candles(rows: list[list]) -> list[Candle]:
    candles = [
        Candle(
            opened_at=int(row[0]) // 1000,
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
        )
        for row in rows
    ]
    candles.sort(key=lambda c: c.opened_at)
    return candles


def fetch_recent(pair: str, days: int = 400) -> list[Candle]:
    symbol = _symbol_for(pair)
    since_ms = int((time.time() - days * 86400) * 1000)
    rows = _fetch_all_klines(symbol, since_ms)
    return _to_candles(rows)


def sync_to_db(conn, pair: str, since: str = "2017-01-01") -> int:
    import calendar
    import datetime

    symbol = _symbol_for(pair)
    since_ms = calendar.timegm(time.strptime(since, "%Y-%m-%d")) * 1000
    rows = _fetch_all_klines(symbol, since_ms)
    candles = _to_candles(rows)

    now = int(time.time())
    count = 0
    for c in candles:
        conn.execute(
            """INSERT INTO candle VALUES ('binance', ?, 1440, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (source_id, pair, interval_min, opened_at) DO UPDATE SET
                 open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close,
                 base_volume=excluded.base_volume, imported_at=excluded.imported_at
               WHERE candle.close != excluded.close""",
            (pair, c.opened_at, c.opened_at + 86400, c.open, c.high, c.low, c.close, c.volume, BINANCE_API, now),
        )
        count += 1
    conn.commit()
    return count


def test_connection() -> dict:
    result = {}
    for pair in PORTFOLIO_PAIRS:
        try:
            candles = fetch_recent(pair, days=10)
            result[pair] = {
                "ok": True,
                "message": f"{len(candles)} dnevnih svijeća, zadnja cijena: {candles[-1].close if candles else '?'}",
            }
        except Exception as err:
            result[pair] = {"ok": False, "message": str(err)}
    return result
