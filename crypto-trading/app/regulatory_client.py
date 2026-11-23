"""Grubi regulatorni rizik-skor: čita javne RSS feedove SEC-a i CFTC-a (američki regulatori s
najvećim utjecajem na kripto tržište), filtrira naslove koji spominju kripto teme, i boduje ih
jednostavnim leksikonom (pozitivne/negativne riječi) - isti pristup kao reddit_client.py.

Ovo NIJE pravna analiza niti zamjena za praćenje stvarnih regulatornih vijesti - tretiraj kao grub,
automatski generiran indikator, ne kao pouzdan zaključak. Za stvarne odluke pročitaj originalne
objave.

NAPOMENA O POUZDANOSTI: RSS URL-ovi i format prema javno poznatim feedovima u trenutku pisanja
koda, nisu uživo testirani u ovom okruženju (nema izlaznog pristupa internetu).
"""
import calendar
import time

import httpx

FEEDS = {
    "REG_SEC": "https://www.sec.gov/news/pressreleases.rss",
    "REG_CFTC": "https://www.cftc.gov/RSS/RSSGP/rssgp.xml",
}

CRYPTO_KEYWORDS = {"crypto", "bitcoin", "ethereum", "digital asset", "blockchain", "token", "stablecoin"}
POSITIVE_WORDS = {"approve", "approval", "clarity", "framework", "guidance", "authorize"}
NEGATIVE_WORDS = {"charge", "charges", "fraud", "lawsuit", "ban", "crackdown", "enforcement", "violation", "penalty", "sue", "suit"}

USER_AGENT = "TenderCryptoResearch/0.1 (istrazivacki alat, kontakt: vlasnik racuna)"


class RegulatoryError(Exception):
    pass


def _fetch_entries(url: str) -> list:
    try:
        import feedparser
    except ImportError as err:
        raise RegulatoryError(f"feedparser nije instaliran: {err}")

    with httpx.Client(timeout=20) as client:
        resp = client.get(url, headers={"User-Agent": USER_AGENT})
    if resp.status_code != 200:
        raise RegulatoryError(f"HTTP {resp.status_code} od {url}: {resp.text[:300]}")

    parsed = feedparser.parse(resp.content)
    if parsed.bozo and not parsed.entries:
        raise RegulatoryError(f"RSS feed {url} nije valjan XML: {parsed.bozo_exception}")
    return parsed.entries


def _score_entry(title: str, summary: str) -> int | None:
    text = f"{title} {summary}".lower()
    if not any(k in text for k in CRYPTO_KEYWORDS):
        return None  # nije relevantno za kripto
    return sum(1 for w in POSITIVE_WORDS if w in text) - sum(1 for w in NEGATIVE_WORDS if w in text)


def fetch_recent(label: str, days: int = 90) -> list[tuple[int, float]]:
    url = FEEDS.get(label)
    if not url:
        raise RegulatoryError(f"Nepoznata oznaka '{label}'.")
    entries = _fetch_entries(url)
    cutoff = time.time() - days * 86400

    by_day: dict[int, list[int]] = {}
    for entry in entries:
        if not getattr(entry, "published_parsed", None):
            continue
        ts = calendar.timegm(entry.published_parsed)
        if ts < cutoff:
            continue
        score = _score_entry(entry.get("title", ""), entry.get("summary", ""))
        if score is None:
            continue
        day_ts = ts - (ts % 86400)
        by_day.setdefault(day_ts, []).append(score)

    points = [(day, float(sum(scores))) for day, scores in by_day.items()]
    points.sort()
    return points


def sync_to_db(conn, label: str) -> int:
    import datetime

    from app.macro_store import save_series

    points = fetch_recent(label, days=36500)  # RSS feed je ionako ograničen na zadnjih N objava
    date_points = [
        (datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%d"), v) for ts, v in points
    ]
    return save_series(conn, "regulatory", label, date_points)


def test_connection() -> dict:
    result = {}
    for label in FEEDS:
        try:
            points = fetch_recent(label, days=30)
            result[label] = {"ok": True, "message": f"{len(points)} dana s relevantnim objavama"}
        except Exception as err:
            result[label] = {"ok": False, "message": str(err)}
    return result
