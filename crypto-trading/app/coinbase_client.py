"""Coinbase API klijent.

NAPOMENA O POUZDANOSTI (isti princip kao TED/EOJN providere u glavnoj Tender aplikaciji): ovo
razvojno okruženje nema izlazni pristup internetu, pa niti javni ni autenticirani Coinbase pozivi
nisu uživo testirani. Endpointi i format JWT autentikacije napisani su prema poznatoj javnoj
dokumentaciji Coinbase Advanced Trade API-ja (CDP API Keys, ES256-potpisan JWT po zahtjevu) u
trenutku pisanja koda. Prije bilo kakvog pravog (a pogotovo live) korištenja, pokreni
"Testiraj vezu" na dashboardu iz okoline koja ima pristup internetu - ako javi grešku, popravak je
izoliran u ovoj datoteci.

Javni cjenovni feed (api.exchange.coinbase.com) ne treba API ključ - koristi se za paper trading.
Privatni pozivi (stanje računa, slanje naloga) trebaju CDP API ključ: naziv ključa oblika
"organizations/{org_id}/apiKeys/{key_id}" i pripadni EC privatni ključ (PEM). Napravi ga u
Coinbase Developer Platform (portal.cdp.coinbase.com) s dopuštenjem "trade" - BEZ dopuštenja za
podizanje sredstava ("withdraw"/"transfer"), da bi šteta u slučaju kompromitacije ključa bila
ograničena samo na trgovanje, ne i na odljev novca s računa.
"""
import time
import uuid

import httpx
import jwt

from app import config

PUBLIC_BASE = "https://api.exchange.coinbase.com"
BROKERAGE_BASE = "https://api.coinbase.com"
BROKERAGE_HOST = "api.coinbase.com"


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


def _build_jwt(method: str, path: str) -> str:
    if not config.COINBASE_API_KEY_NAME or not config.COINBASE_API_PRIVATE_KEY:
        raise CoinbaseError("COINBASE_API_KEY_NAME / COINBASE_API_PRIVATE_KEY nisu postavljeni u .env.")

    now = int(time.time())
    payload = {
        "sub": config.COINBASE_API_KEY_NAME,
        "iss": "cdp",
        "nbf": now,
        "exp": now + 120,
        "uri": f"{method} {BROKERAGE_HOST}{path}",
    }
    headers = {"kid": config.COINBASE_API_KEY_NAME, "nonce": uuid.uuid4().hex}
    return jwt.encode(payload, config.COINBASE_API_PRIVATE_KEY, algorithm="ES256", headers=headers)


def _authenticated_request(method: str, path: str, json_body: dict | None = None) -> dict:
    token = _build_jwt(method, path)
    with httpx.Client(timeout=15) as client:
        resp = client.request(
            method,
            f"{BROKERAGE_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"},
            json=json_body,
        )
    if resp.status_code >= 400:
        raise CoinbaseError(f"HTTP {resp.status_code} od {path}: {resp.text[:500]}")
    return resp.json()


def get_accounts() -> dict:
    return _authenticated_request("GET", "/api/v3/brokerage/accounts")


def place_market_order(product_id: str, side: str, quote_size_eur: float | None = None, base_size: float | None = None) -> dict:
    """side: 'BUY' ili 'SELL'. Kod BUY šalji quote_size_eur (koliko EUR potrošiti),
    kod SELL šalji base_size (koliko jedinice kripto-valute prodati)."""
    order_config: dict = {}
    if side.upper() == "BUY":
        if not quote_size_eur:
            raise CoinbaseError("BUY nalog treba quote_size_eur.")
        order_config = {"market_market_ioc": {"quote_size": f"{quote_size_eur:.2f}"}}
    else:
        if not base_size:
            raise CoinbaseError("SELL nalog treba base_size.")
        order_config = {"market_market_ioc": {"base_size": f"{base_size:.8f}"}}

    body = {
        "client_order_id": uuid.uuid4().hex,
        "product_id": product_id,
        "side": side.upper(),
        "order_configuration": order_config,
    }
    return _authenticated_request("POST", "/api/v3/brokerage/orders", body)


def test_connection() -> dict:
    """Vraća dijagnostiku - ista konvencija kao /api/tender-search/test-connection u Tender aplikaciji."""
    result = {"public_feed": {"ok": False, "message": ""}, "authenticated": {"ok": False, "message": ""}}

    try:
        price = get_public_price("BTC-EUR")
        result["public_feed"] = {"ok": True, "message": f"BTC-EUR = {price}"}
    except Exception as err:
        result["public_feed"] = {"ok": False, "message": str(err)}

    if not config.COINBASE_API_KEY_NAME:
        result["authenticated"] = {"ok": False, "message": "API ključ nije konfiguriran (vidi .env.example)."}
        return result

    try:
        accounts = get_accounts()
        count = len(accounts.get("accounts", []))
        result["authenticated"] = {"ok": True, "message": f"Povezano - {count} računa dohvaćeno."}
    except Exception as err:
        result["authenticated"] = {"ok": False, "message": str(err)}

    return result
