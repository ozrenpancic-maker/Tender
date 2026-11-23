"""CoinGecko - besplatan javni API (bez ključa za osnovne 'public' endpointe, uz rate limit) za
tokenomics podatke. Market cap i cijena zajedno implicitno daju cirkulirajuću ponudu
(market_cap / price) - CoinGecko ne nudi direktno POVIJESNU seriju cirkulirajuće ponude kao
poseban endpoint, pa se izvodi na ovaj način.

UŽIVO TESTIRANO (23.11.2026.) - radi. Besplatni tier ima strog rate limit (cca 10-30 poziva/min) -
sync treba pokretati rijetko, ne u petlji.
"""
import time

import httpx

COINGECKO_BASE = "https://api.coingecko.com/api/v3"

# Oznaka -> CoinGecko coin id.
COINS = {
    "BTC_SUPPLY": "bitcoin",
    "ETH_SUPPLY": "ethereum",
    "SOL_SUPPLY": "solana",
}


class CoinGeckoError(Exception):
    pass


def _fetch_market_chart(coin_id: str, days: str = "365") -> dict:
    with httpx.Client(timeout=20) as client:
        resp = client.get(
            f"{COINGECKO_BASE}/coins/{coin_id}/market_chart",
            params={"vs_currency": "usd", "days": days, "interval": "daily"},
        )
    if resp.status_code != 200:
        raise CoinGeckoError(f"HTTP {resp.status_code} od CoinGecko za {coin_id}: {resp.text[:300]}")
    data = resp.json()
    if "market_caps" not in data or "prices" not in data:
        raise CoinGeckoError(f"Neočekivan CoinGecko odgovor za {coin_id}: {str(data)[:300]}")
    return data


def _derive_supply(data: dict) -> list[tuple[int, float]]:
    prices = {int(t / 1000): p for t, p in data["prices"]}
    caps = {int(t / 1000): c for t, c in data["market_caps"]}
    points = []
    for ts, cap in caps.items():
        price = prices.get(ts)
        if price and price > 0:
            points.append((ts, cap / price))  # implicitna cirkulirajuća ponuda
    points.sort()
    return points


def fetch_recent(label: str, days: int = 365) -> list[tuple[int, float]]:
    coin_id = COINS.get(label, label)
    data = _fetch_market_chart(coin_id, days=str(days))
    return _derive_supply(data)


def sync_to_db(conn, label: str) -> int:
    import datetime

    from app.macro_store import save_series

    coin_id = COINS.get(label, label)
    data = _fetch_market_chart(coin_id, days="max")
    points = _derive_supply(data)
    date_points = [
        (datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%d"), value) for ts, value in points
    ]
    return save_series(conn, "coingecko", label, date_points)


def test_connection() -> dict:
    result = {}
    for label in COINS:
        try:
            points = fetch_recent(label, days=10)
            result[label] = {"ok": True, "message": f"{len(points)} točaka, zadnja ponuda: {points[-1][1] if points else '?'}"}
        except Exception as err:
            result[label] = {"ok": False, "message": str(err)}
    return result
