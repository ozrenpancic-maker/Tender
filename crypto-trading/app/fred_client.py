"""FRED (Federal Reserve Economic Data) - službeni, besplatan API za makro podatke: Fed stopa,
inflacija (CPI), nezaposlenost, BDP. Treba besplatan API ključ: registracija na
https://fred.stlouisfed.org/docs/api/api_key.html, postavi kao FRED_API_KEY u .env.

NAPOMENA O POUZDANOSTI: endpoint/format odgovora napisan prema službenoj FRED API dokumentaciji,
ali nije uživo testiran u ovom okruženju (nema izlaznog pristupa internetu). Pokreni "Testiraj vezu"
iz okoline s internet pristupom prije oslanjanja na ovo.
"""
import time

import httpx

from app.config import FRED_API_KEY

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# Oznaka -> FRED series ID. Dopuni po potrebi (puni popis: https://fred.stlouisfed.org/tags/series).
SERIES = {
    "FEDFUNDS": "FEDFUNDS",  # Federal Funds Effective Rate
    "CPI": "CPIAUCSL",  # Consumer Price Index
    "UNRATE": "UNRATE",  # Nezaposlenost
    "GDP": "GDP",  # Bruto domaći proizvod (kvartalno)
}


class FredError(Exception):
    pass


def _fetch(series_id: str) -> list[dict]:
    if not FRED_API_KEY:
        raise FredError("FRED_API_KEY nije postavljen u .env. Besplatan ključ: fred.stlouisfed.org/docs/api/api_key.html")

    with httpx.Client(timeout=15) as client:
        resp = client.get(
            FRED_BASE,
            params={"series_id": series_id, "api_key": FRED_API_KEY, "file_type": "json"},
        )
    if resp.status_code != 200:
        raise FredError(f"HTTP {resp.status_code} od FRED-a za {series_id}: {resp.text[:300]}")
    data = resp.json()
    observations = data.get("observations")
    if observations is None:
        raise FredError(f"Neočekivan FRED odgovor za {series_id}: {str(data)[:300]}")
    return observations


def fetch_recent(label: str, days: int = 400) -> list[tuple[int, float]]:
    series_id = SERIES.get(label, label)
    observations = _fetch(series_id)
    cutoff = time.time() - days * 86400
    result = []
    for obs in observations:
        if obs.get("value") in (None, "."):
            continue
        try:
            import calendar

            ts = calendar.timegm(time.strptime(obs["date"], "%Y-%m-%d"))
            value = float(obs["value"])
        except (ValueError, KeyError):
            continue
        if ts >= cutoff:
            result.append((ts, value))
    result.sort()
    return result


def sync_to_db(conn, label: str) -> int:
    from app.macro_store import save_series

    series_id = SERIES.get(label, label)
    observations = _fetch(series_id)
    points = [(obs["date"], float(obs["value"])) for obs in observations if obs.get("value") not in (None, ".")]
    return save_series(conn, "fred", label, points)


def test_connection() -> dict:
    result = {}
    for label in SERIES:
        try:
            points = fetch_recent(label, days=60)
            result[label] = {"ok": True, "message": f"{len(points)} točaka, zadnja: {points[-1][1] if points else '?'}"}
        except Exception as err:
            result[label] = {"ok": False, "message": str(err)}
    return result
