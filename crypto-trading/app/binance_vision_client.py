"""Binance Vision - javna bulk arhiva povijesnih svijeća (data.binance.vision), bez ključa, bez
autentikacije, statični CDN (nije podložan istom geografskom ograničenju kao api.binance.com -
REST API vraća HTTP 451 iz ovog okruženja, Vision arhiva radi normalno, provjereno uživo).

Koristi se za ono što `app/binance_history_client.py` (REST API) ne može dati iz ovog okruženja:
- potpunu povijest novog para (npr. XRP) od dana listanja,
- dulju 1h/4h povijest nego nekoliko mjeseci (monthly arhive, ne zahtjeva paginaciju po 1000 redaka).

Format: /data/spot/monthly/klines/{SYMBOL}/{interval}/{SYMBOL}-{interval}-{YYYY}-{MM}.zip - jedan
CSV po mjesecu. Zadnji (nedovršeni) mjesec nema monthly arhivu - koristi se daily arhiva za svaki
dan tog mjeseca kao nadopuna. Mjeseci prije datuma listanja ili budućnost vraćaju 404 - preskoči se."""
import calendar
import io
import time
import zipfile

import httpx

from app.candles import Candle

BASE = "https://data.binance.vision/data/spot"
INTERVAL_MIN = {"1d": 1440, "4h": 240, "1h": 60}


class BinanceVisionError(Exception):
    pass


def _to_seconds(raw_timestamp: int) -> int:
    """Binance je neke exportove od 2025. prebacio s milisekundi na MIKROsekunde (vidi izvorna
    napomena u projektnoj specifikaciji) - otkriveno uživo: monthly arhive iz 2024. imaju
    13-znamenkaste (ms) vrijednosti, daily arhive iz 2026. imaju 16-znamenkaste (µs). Razlikuje se
    po veličini broja, ne po izvoru/datumu arhive (sigurnije provjeriti svaki red)."""
    if raw_timestamp > 10**14:  # ~16 znamenki -> mikrosekunde
        return raw_timestamp // 1_000_000
    return raw_timestamp // 1000  # ~13 znamenki -> milisekunde


def _parse_csv_zip(content: bytes) -> list[Candle]:
    candles = []
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        name = zf.namelist()[0]
        text = zf.read(name).decode("utf-8")
    for line in text.splitlines():
        parts = line.split(",")
        if len(parts) < 6 or not parts[0].strip('"').isdigit():
            continue  # header redak (noviji exporti imaju nazive stupaca) - preskoči
        raw_timestamp = int(parts[0].strip('"'))
        candles.append(
            Candle(
                opened_at=_to_seconds(raw_timestamp),
                open=float(parts[1].strip('"')),
                high=float(parts[2].strip('"')),
                low=float(parts[3].strip('"')),
                close=float(parts[4].strip('"')),
                volume=float(parts[5].strip('"')),
            )
        )
    return candles


def _get(url: str) -> bytes | None:
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        resp = client.get(url)
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        raise BinanceVisionError(f"HTTP {resp.status_code} za {url}")
    return resp.content


def _fetch_monthly(symbol: str, interval: str, year: int, month: int) -> list[Candle] | None:
    url = f"{BASE}/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{year:04d}-{month:02d}.zip"
    content = _get(url)
    return _parse_csv_zip(content) if content else None


def _fetch_daily(symbol: str, interval: str, year: int, month: int, day: int) -> list[Candle] | None:
    url = f"{BASE}/daily/klines/{symbol}/{interval}/{symbol}-{interval}-{year:04d}-{month:02d}-{day:02d}.zip"
    content = _get(url)
    return _parse_csv_zip(content) if content else None


def _month_iter(start_year: int, start_month: int, end_year: int, end_month: int):
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def fetch_history(symbol: str, interval: str, since_year: int, since_month: int) -> list[Candle]:
    """Vraća SVE svijeće od since_year-since_month do danas (uključujući nedovršeni tekući mjesec
    preko dnevnih arhiva). Preskoči mjesece koji vrate 404 (prije listanja na Binanceu)."""
    if interval not in INTERVAL_MIN:
        raise BinanceVisionError(f"Nepodržan interval '{interval}'. Dostupno: {list(INTERVAL_MIN)}")
    now = time.gmtime()
    all_candles: list[Candle] = []
    for year, month in _month_iter(since_year, since_month, now.tm_year, now.tm_mon):
        candles = _fetch_monthly(symbol, interval, year, month)
        if candles is None:
            if (year, month) == (now.tm_year, now.tm_mon):
                # tekući mjesec - monthly arhiva još ne postoji, pokupi dan po dan preko daily arhive
                days_so_far = now.tm_mday
                for day in range(1, days_so_far):
                    daily = _fetch_daily(symbol, interval, year, month, day)
                    if daily:
                        all_candles.extend(daily)
            continue  # 404 prije listanja na Binanceu - preskoči, ne greška
        all_candles.extend(candles)
    all_candles.sort(key=lambda c: c.opened_at)
    return all_candles


def sync_to_db(conn, pair: str, symbol: str, interval: str, since_year: int, since_month: int) -> int:
    """Sprema u POSTOJEĆU `candle` tablicu, source_id='binance' - isti oblik kao
    `app/binance_history_client.py`, pa odmah radi sa svim postojećim strategijama/backtestom."""
    candles = fetch_history(symbol, interval, since_year, since_month)
    interval_min = INTERVAL_MIN[interval]
    interval_seconds = interval_min * 60
    now = int(time.time())
    count = 0
    for c in candles:
        conn.execute(
            """INSERT INTO candle VALUES ('binance', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (source_id, pair, interval_min, opened_at) DO UPDATE SET
                 open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close,
                 base_volume=excluded.base_volume, imported_at=excluded.imported_at
               WHERE candle.close != excluded.close""",
            (
                pair,
                interval_min,
                c.opened_at,
                c.opened_at + interval_seconds,
                c.open,
                c.high,
                c.low,
                c.close,
                c.volume,
                "https://data.binance.vision",
                now,
            ),
        )
        count += 1
    conn.commit()
    return count


def test_connection() -> dict:
    try:
        candles = _fetch_monthly("BTCUSDT", "1d", 2024, 1)
        ok = bool(candles)
        return {"ok": ok, "message": f"{len(candles)} svijeća u test arhivi (BTCUSDT 1d 2024-01)." if ok else "Prazan odgovor."}
    except Exception as err:
        return {"ok": False, "message": str(err)}
