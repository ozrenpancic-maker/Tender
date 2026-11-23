"""Reddit sentiment preko službenog OAuth2 (client credentials) API-ja - besplatna registracija
"script" aplikacije na reddit.com/prefs/apps daje REDDIT_CLIENT_ID i REDDIT_CLIENT_SECRET.

Sentiment NIJE iz treniranog NLP modela - to bi zahtijevalo dodatnu infrastrukturu/trošak. Umjesto
toga koristi se jednostavan leksikon (brojanje "bullish"/"bearish" riječi u naslovima objava).
Ovo je namjerno grubo i transparentno, ne lažno precizno - tretiraj kao grubi indikator raspoloženja
zajednice, ne kao pouzdanu klasifikaciju.

NAPOMENA O POUZDANOSTI: endpoint prema službenoj Reddit API dokumentaciji, nije uživo testirano u
ovom okruženju (nema izlaznog pristupa internetu).
"""
import calendar
import datetime
import time

import httpx

from app.config import REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET

USER_AGENT = "TenderCryptoResearch/0.1 (istrazivacki alat, kontakt: vlasnik racuna)"

SUBREDDITS = {
    "REDDIT_BTC": "Bitcoin",
    "REDDIT_CRYPTO": "CryptoCurrency",
}

BULLISH_WORDS = {"moon", "bullish", "buy", "breakout", "rally", "pump", "ath", "undervalued", "accumulate"}
BEARISH_WORDS = {"dump", "bearish", "sell", "crash", "capitulation", "scam", "rug", "overvalued", "panic"}


class RedditError(Exception):
    pass


def _get_token() -> str:
    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        raise RedditError("REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET nisu postavljeni u .env (vidi reddit.com/prefs/apps).")

    with httpx.Client(timeout=15) as client:
        resp = client.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": USER_AGENT},
        )
    if resp.status_code != 200:
        raise RedditError(f"HTTP {resp.status_code} pri dohvatu Reddit tokena: {resp.text[:300]}")
    token = resp.json().get("access_token")
    if not token:
        raise RedditError(f"Reddit odgovor nema access_token: {resp.text[:300]}")
    return token


def _score_text(text: str) -> int:
    lowered = text.lower()
    return sum(1 for w in BULLISH_WORDS if w in lowered) - sum(1 for w in BEARISH_WORDS if w in lowered)


def _fetch_posts(subreddit: str, limit: int = 100) -> list[dict]:
    token = _get_token()
    with httpx.Client(timeout=15) as client:
        resp = client.get(
            f"https://oauth.reddit.com/r/{subreddit}/new",
            params={"limit": limit},
            headers={"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT},
        )
    if resp.status_code != 200:
        raise RedditError(f"HTTP {resp.status_code} od Reddita za r/{subreddit}: {resp.text[:300]}")
    data = resp.json()
    children = data.get("data", {}).get("children")
    if children is None:
        raise RedditError(f"Neočekivan Reddit odgovor za r/{subreddit}: {str(data)[:300]}")
    return [c["data"] for c in children]


def _aggregate_daily_sentiment(posts: list[dict]) -> list[tuple[int, float]]:
    by_day: dict[int, list[int]] = {}
    for post in posts:
        created = int(post.get("created_utc", 0))
        day_ts = created - (created % 86400)
        score = _score_text(post.get("title", ""))
        by_day.setdefault(day_ts, []).append(score)
    points = [(day, sum(scores) / len(scores)) for day, scores in by_day.items()]
    points.sort()
    return points


def fetch_recent(label: str, days: int = 30) -> list[tuple[int, float]]:
    subreddit = SUBREDDITS.get(label, label)
    posts = _fetch_posts(subreddit, limit=100)  # Reddit "new" listing - zadnjih ~100 objava
    points = _aggregate_daily_sentiment(posts)
    cutoff = time.time() - days * 86400
    return [(ts, v) for ts, v in points if ts >= cutoff]


def sync_to_db(conn, label: str) -> int:
    from app.macro_store import save_series

    points = fetch_recent(label, days=36500)  # "new" listing je ionako ograničen na zadnjih ~100 objava
    date_points = [
        (datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%d"), v) for ts, v in points
    ]
    return save_series(conn, "reddit", label, date_points)


def test_connection() -> dict:
    result = {}
    for label in SUBREDDITS:
        try:
            points = fetch_recent(label, days=7)
            result[label] = {"ok": True, "message": f"{len(points)} dana s podacima, zadnji skor: {points[-1][1] if points else '?'}"}
        except Exception as err:
            result[label] = {"ok": False, "message": str(err)}
    return result
