"""Google Trends preko pytrends - NEslužbeni "pseudo-API" koji oponaša web sučelje Google Trendsa
(scraping pristup, ne službeni Google API). Google redovito mijenja zaštite protiv automatiziranog
pristupa pa ovo može prestati raditi bez najave, vraćati prazne rezultate ili biti rate-limitano.

Koristi se za "nagli porast interesa" signal (porast pretraga za 'bitcoin'/'crypto' često prethodi
velikom pokretu cijene - iz korisnikovog popisa čimbenika).

NAPOMENA O POUZDANOSTI: nije uživo testirano u ovom okruženju (nema izlaznog pristupa internetu).
Ovo je od svih dodanih izvora najkrhkiji - ako "Testiraj vezu" ne uspije, prvo provjeri je li
pytrends i dalje održavan/kompatibilan s trenutnom Google Trends stranicom prije traženja bugova
u ovom kodu.
"""
import calendar
import time

KEYWORDS = {
    "BITCOIN_TREND": "bitcoin",
    "CRYPTO_TREND": "crypto",
    "ALTCOIN_TREND": "altcoin",
}


class TrendsError(Exception):
    pass


def _fetch_interest_over_time(keyword: str, timeframe: str = "today 12-m"):
    try:
        from pytrends.request import TrendReq
    except ImportError as err:
        raise TrendsError(f"pytrends nije instaliran: {err}")

    try:
        pytrends = TrendReq(hl="en-US", tz=0)
        pytrends.build_payload([keyword], timeframe=timeframe)
        df = pytrends.interest_over_time()
    except Exception as err:
        raise TrendsError(f"Google Trends upit nije uspio za '{keyword}': {err}")

    if df is None or df.empty:
        raise TrendsError(f"Google Trends je vratio prazan rezultat za '{keyword}' - možda rate limit.")
    return df


def fetch_recent(label: str, days: int = 365) -> list[tuple[int, float]]:
    keyword = KEYWORDS.get(label, label)
    df = _fetch_interest_over_time(keyword, timeframe="today 12-m" if days <= 365 else "today 5-y")
    cutoff = time.time() - days * 86400
    points = []
    for date, row in df.iterrows():
        ts = calendar.timegm(date.timetuple())
        if ts >= cutoff:
            points.append((ts, float(row[keyword])))
    points.sort()
    return points


def sync_to_db(conn, label: str) -> int:
    import datetime

    from app.macro_store import save_series

    keyword = KEYWORDS.get(label, label)
    df = _fetch_interest_over_time(keyword, timeframe="today 5-y")
    points = [
        (datetime.datetime.fromtimestamp(calendar.timegm(date.timetuple()), datetime.timezone.utc).strftime("%Y-%m-%d"), float(row[keyword]))
        for date, row in df.iterrows()
    ]
    return save_series(conn, "google_trends", label, points)


def test_connection() -> dict:
    result = {}
    for label in KEYWORDS:
        try:
            points = fetch_recent(label, days=30)
            result[label] = {"ok": True, "message": f"{len(points)} točaka, zadnja: {points[-1][1] if points else '?'}"}
        except Exception as err:
            result[label] = {"ok": False, "message": str(err)}
    return result
