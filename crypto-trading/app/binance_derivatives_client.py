"""Binance Futures javni API (bez ključa) za funding rate i open interest - derivati/leverage
sentiment podaci spomenuti u korisnikovom popisu ("short squeeze", "long squeeze", "pregrijano
tržište"). Za razliku od order book dubine, povijest funding ratea JE besplatno dostupna godinama
unatrag, pa se može koristiti i za backtest, ne samo uživo promatranje.

Open interest povijest (`/futures/data/openInterestHist`) je ograničena na zadnjih ~30 dana od
strane Binancea - korisno za paper/live, ali nedovoljno za dugi backtest, pa nije uključeno u
`needs_series` mehanizam (koji pretpostavlja dovoljno povijesti za in-sample/out-of-sample testove).

UŽIVO TESTIRANO (23.11.2026., okruženje s izlaznim internet pristupom): HTTP 451 - "Service
unavailable from a restricted location" po Binanceovim Uvjetima korištenja. Ovo NIJE problem s
internet pristupom ni s kodom - Binance (fapi.binance.com i api.binance.com) geografski blokira
ovu konkretnu lokaciju/IP raspon, neovisno o tome ima li okruženje internet. `data.binance.vision`
(statična bulk arhiva, vidi `app/binance_vision_client.py`) NIJE pod istim ograničenjem i radi.

NAPOMENA O POUZDANOSTI: endpointi prema javnoj Binance Futures API dokumentaciji, nisu uživo
testirani u ovom okruženju (nema izlaznog pristupa internetu).
"""
import time

import httpx

FAPI_BASE = "https://fapi.binance.com"

# Oznaka -> Binance futures simbol.
FUNDING_SYMBOLS = {
    "BTC_FUNDING": "BTCUSDT",
    "ETH_FUNDING": "ETHUSDT",
    "SOL_FUNDING": "SOLUSDT",
}


class BinanceDerivativesError(Exception):
    pass


def _fetch_funding_page(symbol: str, start_time_ms: int | None, limit: int = 1000) -> list[dict]:
    params = {"symbol": symbol, "limit": limit}
    if start_time_ms is not None:
        params["startTime"] = start_time_ms
    with httpx.Client(timeout=20) as client:
        resp = client.get(f"{FAPI_BASE}/fapi/v1/fundingRate", params=params)
    if resp.status_code != 200:
        raise BinanceDerivativesError(f"HTTP {resp.status_code} od Binance futures za {symbol}: {resp.text[:300]}")
    data = resp.json()
    if not isinstance(data, list):
        raise BinanceDerivativesError(f"Neočekivan Binance futures odgovor za {symbol}: {str(data)[:300]}")
    return data


def _fetch_all_funding(symbol: str, since_ms: int) -> list[dict]:
    all_rows = []
    cursor = since_ms
    now_ms = int(time.time() * 1000)
    while cursor < now_ms:
        page = _fetch_funding_page(symbol, cursor)
        if not page:
            break
        all_rows.extend(page)
        last_time = page[-1]["fundingTime"]
        if last_time <= cursor:
            break  # zaštita od beskonačne petlje ako API vrati manje od limit redaka bez napretka
        cursor = last_time + 1
        if len(page) < 1000:
            break
    return all_rows


def _daily_average(rows: list[dict]) -> list[tuple[int, float]]:
    by_day: dict[int, list[float]] = {}
    for row in rows:
        ts = int(row["fundingTime"]) // 1000
        day_ts = ts - (ts % 86400)
        by_day.setdefault(day_ts, []).append(float(row["fundingRate"]))
    points = [(day, sum(rates) / len(rates)) for day, rates in by_day.items()]
    points.sort()
    return points


def fetch_recent(label: str, days: int = 400) -> list[tuple[int, float]]:
    symbol = FUNDING_SYMBOLS.get(label, label)
    since_ms = int((time.time() - days * 86400) * 1000)
    rows = _fetch_all_funding(symbol, since_ms)
    return _daily_average(rows)


def fetch_open_interest(label: str) -> float:
    """Trenutni open interest (jedna vrijednost, ne povijest) - za paper/live prikaz, ne backtest."""
    symbol = FUNDING_SYMBOLS.get(label, label)
    with httpx.Client(timeout=15) as client:
        resp = client.get(f"{FAPI_BASE}/fapi/v1/openInterest", params={"symbol": symbol})
    if resp.status_code != 200:
        raise BinanceDerivativesError(f"HTTP {resp.status_code} od Binance futures za {symbol}: {resp.text[:300]}")
    data = resp.json()
    if "openInterest" not in data:
        raise BinanceDerivativesError(f"Neočekivan odgovor za open interest {symbol}: {str(data)[:300]}")
    return float(data["openInterest"])


def sync_to_db(conn, label: str) -> int:
    import datetime

    from app.macro_store import save_series

    symbol = FUNDING_SYMBOLS.get(label, label)
    # Binance USDT-M perpetualni ugovori postoje od cca 2019-2020 ovisno o paru - krećemo od 2019.
    since_ms = int(datetime.datetime(2019, 1, 1, tzinfo=datetime.timezone.utc).timestamp() * 1000)
    rows = _fetch_all_funding(symbol, since_ms)
    points = _daily_average(rows)
    date_points = [
        (datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%d"), value) for ts, value in points
    ]
    return save_series(conn, "binance_futures", label, date_points)


def test_connection() -> dict:
    result = {}
    for label in FUNDING_SYMBOLS:
        try:
            points = fetch_recent(label, days=10)
            oi = fetch_open_interest(label)
            result[label] = {
                "ok": True,
                "message": f"{len(points)} dana funding podataka, zadnji: {points[-1][1] if points else '?'}, trenutni OI: {oi}",
            }
        except Exception as err:
            result[label] = {"ok": False, "message": str(err)}
    return result
