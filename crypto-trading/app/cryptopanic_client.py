"""CryptoPanic - agregator kripto vijesti s besplatnim tierom (treba besplatnu registraciju:
cryptopanic.com/developers/api/). Za razliku od našeg grubog leksikona (reddit_client.py,
regulatory_client.py), CryptoPanic ima stvarne glasove zajednice po objavi (bullish/bearish/
important) - kvalitetniji, crowd-sourced signal umjesto brojanja riječi.

NAPOMENA O POUZDANOSTI: endpoint prema CryptoPanic API v1 dokumentaciji u trenutku pisanja koda,
nije uživo testiran u ovom okruženju (nema izlaznog pristupa internetu). CryptoPanic je mijenjao
API verzije u prošlosti - ako "Testiraj vezu" ne uspije, prvo provjeri trenutnu dokumentaciju na
cryptopanic.com/developers/api/ prije traženja bugova u ovom kodu.
"""
import calendar
import time

import httpx

from app.config import CRYPTOPANIC_API_KEY

CRYPTOPANIC_BASE = "https://cryptopanic.com/api/v1/posts/"

# Oznaka -> CryptoPanic "currencies" filter (kod valute).
FILTERS = {
    "NEWS_BTC": "BTC",
    "NEWS_ETH": "ETH",
    "NEWS_GENERAL": "",  # bez filtra - opća kripto tržišta
}


class CryptoPanicError(Exception):
    pass


def _fetch_posts(currency: str, pages: int = 3) -> list[dict]:
    if not CRYPTOPANIC_API_KEY:
        raise CryptoPanicError("CRYPTOPANIC_API_KEY nije postavljen u .env (besplatna registracija: cryptopanic.com/developers/api/).")

    posts = []
    url = CRYPTOPANIC_BASE
    params = {"auth_token": CRYPTOPANIC_API_KEY, "public": "true"}
    if currency:
        params["currencies"] = currency

    with httpx.Client(timeout=20) as client:
        for _ in range(pages):
            resp = client.get(url, params=params)
            if resp.status_code != 200:
                raise CryptoPanicError(f"HTTP {resp.status_code} od CryptoPanic: {resp.text[:300]}")
            data = resp.json()
            results = data.get("results")
            if results is None:
                raise CryptoPanicError(f"Neočekivan CryptoPanic odgovor: {str(data)[:300]}")
            posts.extend(results)
            next_url = data.get("next")
            if not next_url:
                break
            url, params = next_url, {}  # "next" već sadrži sve query parametre

    return posts


def _score_post(post: dict) -> int:
    votes = post.get("votes", {})
    positive = votes.get("positive", 0) + votes.get("liked", 0)
    negative = votes.get("negative", 0) + votes.get("disliked", 0) + votes.get("toxic", 0)
    return positive - negative


def _aggregate_daily(posts: list[dict]) -> list[tuple[int, float]]:
    by_day: dict[int, list[int]] = {}
    for post in posts:
        published = post.get("published_at")
        if not published:
            continue
        try:
            ts = calendar.timegm(time.strptime(published[:19], "%Y-%m-%dT%H:%M:%S"))
        except ValueError:
            continue
        day_ts = ts - (ts % 86400)
        by_day.setdefault(day_ts, []).append(_score_post(post))
    points = [(day, sum(scores) / len(scores)) for day, scores in by_day.items()]
    points.sort()
    return points


def fetch_recent(label: str, days: int = 30) -> list[tuple[int, float]]:
    currency = FILTERS.get(label, label)
    posts = _fetch_posts(currency, pages=5)
    points = _aggregate_daily(posts)
    cutoff = time.time() - days * 86400
    return [(ts, v) for ts, v in points if ts >= cutoff]


def sync_to_db(conn, label: str) -> int:
    import datetime

    from app.macro_store import save_series

    points = fetch_recent(label, days=36500)  # API ionako vraća samo nedavne objave
    date_points = [
        (datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%d"), v) for ts, v in points
    ]
    return save_series(conn, "cryptopanic", label, date_points)


def test_connection() -> dict:
    result = {}
    for label in FILTERS:
        try:
            points = fetch_recent(label, days=7)
            result[label] = {"ok": True, "message": f"{len(points)} dana s objavama, zadnji skor: {points[-1][1] if points else '?'}"}
        except Exception as err:
            result[label] = {"ok": False, "message": str(err)}
    return result
