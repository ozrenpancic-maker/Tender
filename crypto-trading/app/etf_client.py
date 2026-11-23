"""Dnevni neto tokovi novca u/iz spot Bitcoin/Ethereum ETF-ova. Nema čistog besplatnog službenog
API-ja za ovo (BlackRock/Fidelity/Ark/Grayscale ne objavljuju zajednički feed) - umjesto toga
scrapa se javno dostupna tablica s farside.co.uk, uobičajen besplatan izvor za ovaj podatak.

UŽIVO TESTIRANO (23.11.2026., okruženje s izlaznim internet pristupom): HTTP 403 - farside.co.uk
je iza Cloudflare zaštite protiv botova ("Just a moment..." JS-challenge stranica), ne vraća
stvarni HTML s tablicom čak i uz normalan internet pristup. To znači da `httpx` (bez izvršavanja
JavaScripta) ovdje ne može proći - treba headless preglednik (Playwright/Selenium) ili drugi izvor
podataka. Provjeri i Uvjete korištenja te stranice prije ikakvog automatiziranog pristupa.
"""
import re
import time

import httpx

FARSIDE_URLS = {
    "BTC_ETF_FLOW": "https://farside.co.uk/btc/",
    "ETH_ETF_FLOW": "https://farside.co.uk/eth/",
}

USER_AGENT = "TenderCryptoResearch/0.1 (istrazivacki alat, kontakt: vlasnik racuna)"


class EtfError(Exception):
    pass


def _fetch_html(url: str) -> str:
    with httpx.Client(timeout=20) as client:
        resp = client.get(url, headers={"User-Agent": USER_AGENT})
    if resp.status_code != 200:
        raise EtfError(f"HTTP {resp.status_code} od {url}: {resp.text[:300]}")
    return resp.text


def _parse_total_flows(html: str) -> list[tuple[str, float]]:
    """Traži retke tablice s datumom i "Total" stupcem (ukupan dnevni neto tok u milijunima USD).
    Format stranice nije uživo potvrđen - ako ovo ne uspije, pogledaj sirovi HTML (vidi
    `_fetch_html` poziv u ručnom debugiranju) i prilagodi ovaj parser."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    results = []
    date_pattern = re.compile(r"\d{1,2}\s+\w{3}\s+\d{4}")
    for row in soup.select("table tr"):
        cells = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cells) < 2:
            continue
        if not date_pattern.search(cells[0]):
            continue
        try:
            total = float(cells[-1].replace(",", "").replace("(", "-").replace(")", ""))
        except ValueError:
            continue
        results.append((cells[0], total))
    if not results:
        raise EtfError("Nijedan redak tablice nije prepoznat - HTML struktura farside.co.uk se vjerojatno promijenila.")
    return results


def fetch_recent(label: str, days: int = 90) -> list[tuple[int, float]]:
    import calendar
    import datetime as dt

    url = FARSIDE_URLS.get(label)
    if not url:
        raise EtfError(f"Nepoznata oznaka '{label}'.")
    html = _fetch_html(url)
    rows = _parse_total_flows(html)
    cutoff = time.time() - days * 86400
    points = []
    for date_str, value in rows:
        try:
            ts = calendar.timegm(dt.datetime.strptime(date_str, "%d %b %Y").timetuple())
        except ValueError:
            continue
        if ts >= cutoff:
            points.append((ts, value))
    points.sort()
    return points


def sync_to_db(conn, label: str) -> int:
    import calendar
    import datetime as dt

    from app.macro_store import save_series

    url = FARSIDE_URLS.get(label)
    if not url:
        raise EtfError(f"Nepoznata oznaka '{label}'.")
    html = _fetch_html(url)
    rows = _parse_total_flows(html)
    date_points = []
    for date_str, value in rows:
        try:
            ts = calendar.timegm(dt.datetime.strptime(date_str, "%d %b %Y").timetuple())
        except ValueError:
            continue
        date_points.append((dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d"), value))
    return save_series(conn, "etf_flow", label, date_points)


def test_connection() -> dict:
    result = {}
    for label in FARSIDE_URLS:
        try:
            points = fetch_recent(label, days=14)
            result[label] = {"ok": True, "message": f"{len(points)} dana, zadnji tok: {points[-1][1] if points else '?'} mil. USD"}
        except Exception as err:
            result[label] = {"ok": False, "message": str(err)}
    return result
