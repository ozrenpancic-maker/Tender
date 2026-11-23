"""Coinbase API klijent - ISKLJUČIVO javni (read-only) cjenovni feed, bez ključa.

NAPOMENA (KriptoMVP 4.4 nepromjenjiva pravila): aplikacija je savjetnik/simulator, nikad ne
izvršava prave naloge i ne traži Coinbase trgovačke API ključeve niti pristup računu/novčaniku.
Autenticirani dio (JWT, stanje računa, slanje naloga) koji je ovdje prije postojao je UKLONJEN -
vidi git povijest ove datoteke i `live_engine.py` ako ga treba za referencu.

NAPOMENA O POUZDANOSTI: ovo razvojno okruženje nema izlazni pristup internetu, pa javni Coinbase
pozivi nisu uživo testirani. Endpointi su napisani prema poznatoj javnoj dokumentaciji Coinbase
Exchange API-ja u trenutku pisanja koda. Prije pravog korištenja pokreni "Testiraj vezu" na
dashboardu iz okoline koja ima pristup internetu - ako javi grešku, popravak je izoliran ovdje.
"""
import time

import httpx

PUBLIC_BASE = "https://api.exchange.coinbase.com"


class CoinbaseError(Exception):
    pass


def get_public_price(product_id: str) -> float:
    """product_id npr. 'BTC-EUR'. Ne treba API ključ."""
    with httpx.Client(timeout=10) as client:
        resp = client.get(f"{PUBLIC_BASE}/products/{product_id}/ticker")
    if resp.status_code != 200:
        raise CoinbaseError(f"HTTP {resp.status_code} od {PUBLIC_BASE}: {resp.text[:300]}")
    data = resp.json()
    price = data.get("price")
    if price is None:
        raise CoinbaseError(f"Odgovor nema polje 'price': {data}")
    return float(price)


def to_product_id(pair: str) -> str:
    """'BTC/EUR' -> 'BTC-EUR' (format koji Coinbase koristi u URL-ovima)."""
    return pair.replace("/", "-")


def get_public_daily_candles(product_id: str, days: int = 120):
    """Vraća zatvorene dnevne svijeće (zadnja, nedovršena svijeća za danas se izbacuje).
    Koristi javni Coinbase Exchange 'candles' endpoint, format [time, low, high, open, close, volume]."""
    from app.candles import Candle

    now = int(time.time())
    start = now - days * 86400
    with httpx.Client(timeout=15) as client:
        resp = client.get(
            f"{PUBLIC_BASE}/products/{product_id}/candles",
            params={"granularity": 86400, "start": start, "end": now},
        )
    if resp.status_code != 200:
        raise CoinbaseError(f"HTTP {resp.status_code} od candles endpointa: {resp.text[:300]}")
    rows = resp.json()
    if not isinstance(rows, list):
        raise CoinbaseError(f"Neočekivan oblik odgovora candles endpointa: {rows}")

    candles = [
        Candle(opened_at=int(r[0]), low=float(r[1]), high=float(r[2]), open=float(r[3]), close=float(r[4]), volume=float(r[5]))
        for r in rows
    ]
    candles.sort(key=lambda c: c.opened_at)
    # Izbaci posljednju svijeću ako dan još nije završio (izbjegava odluke na nedovršenim podacima).
    if candles and candles[-1].opened_at + 86400 > now:
        candles = candles[:-1]
    return candles


def test_connection() -> dict:
    """Vraća dijagnostiku - ista konvencija kao /api/tender-search/test-connection u Tender aplikaciji."""
    result = {"public_feed": {"ok": False, "message": ""}}
    try:
        price = get_public_price("BTC-EUR")
        result["public_feed"] = {"ok": True, "message": f"BTC-EUR = {price}"}
    except Exception as err:
        result["public_feed"] = {"ok": False, "message": str(err)}
    return result
