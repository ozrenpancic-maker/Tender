"""Coinbase API klijent - ISKLJUČIVO javni (read-only) cjenovni feed, bez ključa.

NAPOMENA (KriptoMVP 4.4 nepromjenjiva pravila): aplikacija je savjetnik/simulator, nikad ne
izvršava prave naloge i ne traži Coinbase trgovačke API ključeve niti pristup računu/novčaniku.
Autenticirani dio (JWT, stanje računa, slanje naloga) koji je ovdje prije postojao je UKLONJEN -
vidi git povijest ove datoteke i `live_engine.py` ako ga treba za referencu.

UŽIVO TESTIRANO (23.11.2026., okruženje s izlaznim internet pristupom) - radi, dobivena stvarna
BTC-EUR cijena preko javnog cjenovnog feeda."""
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


def get_public_ticker(product_id: str) -> dict:
    """Isti endpoint kao get_public_price, ali vraća i bid/ask (uživo potvrđeno da ih Coinbase
    Exchange ticker vraća) - za realniju simulaciju izvršenja (vidi app/costs.py). Za HISTORIJSKI
    backtest ovo NE postoji - povijesne OHLC svijeće nemaju bid/ask, samo uživo simulacija (paper
    trading, auto-trader) može ovo koristiti.

    `age_seconds`: koliko je star Coinbaseov 'time' (zadnja trgovina) u odnosu na SAD - koristi se
    za otkrivanje "zastarjelih kotacija" (ChatGPT savjet, točka 4) kad feed vraća uspješan HTTP
    odgovor, ali sa starim/zamrznutim podatkom (npr. par bez prometa, ili problem na Coinbaseovoj
    strani koji nije prava mrežna greška)."""
    import datetime

    with httpx.Client(timeout=10) as client:
        resp = client.get(f"{PUBLIC_BASE}/products/{product_id}/ticker")
    if resp.status_code != 200:
        raise CoinbaseError(f"HTTP {resp.status_code} od {PUBLIC_BASE}: {resp.text[:300]}")
    data = resp.json()
    price, bid, ask, ts = data.get("price"), data.get("bid"), data.get("ask"), data.get("time")
    if price is None or bid is None or ask is None:
        raise CoinbaseError(f"Odgovor nema price/bid/ask: {data}")
    age_seconds = None
    if ts:
        try:
            trade_time = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
            age_seconds = (datetime.datetime.now(datetime.timezone.utc) - trade_time).total_seconds()
        except ValueError:
            pass
    return {"price": float(price), "bid": float(bid), "ask": float(ask), "age_seconds": age_seconds}


def to_product_id(pair: str) -> str:
    """'BTC/EUR' -> 'BTC-EUR' (format koji Coinbase koristi u URL-ovima). 'XXX/USDT' -> 'XXX-USD'
    jer Coinbase NEMA -USDT par za svaki coin u portfelju - provjereno uživo: SUI, PEPE, POL i ALGO
    postoje na Coinbaseu SAMO kao -USD, ne -USDT (vraćaju HTTP 404 na -USDT), dok npr. BTC/XRP/DOGE/
    NEAR imaju oba pa se razlika dosad nije primijetila. USDT≈USD pretpostavka je ovdje sigurna jer
    se Coinbase cijena koristi SAMO za live fill cijenu (ML značajke/label i dalje koriste stvarne
    USDT podatke s Binancea - vidi README 'Uživo dohvat podataka')."""
    base, quote = pair.split("/")
    if quote == "USDT":
        quote = "USD"
    return f"{base}-{quote}"


VALID_GRANULARITIES = {60, 300, 900, 3600, 21600, 86400}  # 1min/5min/15min/1h/6h/1d - Coinbase ne nudi 4h izravno


def get_public_candles(product_id: str, granularity: int, lookback_seconds: int):
    """Vraća zatvorene svijeće (zadnja, nedovršena svijeća se izbacuje) za zadanu granulaciju
    (sekunde). Koristi javni Coinbase Exchange 'candles' endpoint, format
    [time, low, high, open, close, volume]. Coinbase vraća max ~300 svijeća po pozivu."""
    from app.candles import Candle

    if granularity not in VALID_GRANULARITIES:
        raise CoinbaseError(f"Nepodržana granulacija {granularity}. Dostupno: {sorted(VALID_GRANULARITIES)}")
    now = int(time.time())
    start = now - lookback_seconds
    with httpx.Client(timeout=15) as client:
        resp = client.get(
            f"{PUBLIC_BASE}/products/{product_id}/candles",
            params={"granularity": granularity, "start": start, "end": now},
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
    # Izbaci posljednju svijeću ako razdoblje još nije završilo (izbjegava odluke na nedovršenim podacima).
    if candles and candles[-1].opened_at + granularity > now:
        candles = candles[:-1]
    return candles


def get_public_candles_paginated(product_id: str, granularity: int, lookback_seconds: int):
    """Isto kao get_public_candles, ali bez Coinbaseovog ograničenja od max ~300 svijeća po
    pozivu - dijeli traženo razdoblje na više sekvencijalnih poziva unatrag kroz vrijeme."""
    from app.candles import Candle

    max_per_call = 290 * granularity  # malo ispod stvarnog limita (300), sigurnosna margina
    now = int(time.time())
    window_end = now
    all_candles: list[Candle] = []
    remaining = lookback_seconds
    while remaining > 0:
        window_seconds = min(remaining, max_per_call)
        window_start = window_end - window_seconds
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                f"{PUBLIC_BASE}/products/{product_id}/candles",
                params={"granularity": granularity, "start": window_start, "end": window_end},
            )
        if resp.status_code != 200:
            raise CoinbaseError(f"HTTP {resp.status_code} od candles endpointa: {resp.text[:300]}")
        rows = resp.json()
        all_candles.extend(
            Candle(opened_at=int(r[0]), low=float(r[1]), high=float(r[2]), open=float(r[3]), close=float(r[4]), volume=float(r[5]))
            for r in rows
        )
        window_end = window_start
        remaining -= window_seconds

    all_candles.sort(key=lambda c: c.opened_at)
    # ukloni duplikate na granicama prozora, izbaci nedovršenu zadnju svijeću
    deduped = []
    seen = set()
    for c in all_candles:
        if c.opened_at not in seen:
            seen.add(c.opened_at)
            deduped.append(c)
    if deduped and deduped[-1].opened_at + granularity > now:
        deduped = deduped[:-1]
    return deduped


def get_public_daily_candles(product_id: str, days: int = 120):
    """Zadržano za postojeće pozivatelje (paper_engine.py) - isto što i get_public_candles s
    granularity=86400."""
    return get_public_candles(product_id, 86400, days * 86400)


def get_product_constraints(product_id: str) -> dict:
    """Stvarna ograničenja veličine naloga za ovaj par (ChatGPT savjet, točka 5) - minimalan iznos
    naloga (`min_market_funds`, u kotirajućoj valuti) i najmanji korak količine baznog asseta
    (`base_increment`, npr. 1 za PEPE - ne može se kupiti 0,5 PEPE). Realna simulacija ne smije
    tiho pretpostaviti da se može kupiti/prodati bilo koja razlomljena količina - pravi nalog te
    veličine bi Coinbase odbio."""
    with httpx.Client(timeout=10) as client:
        resp = client.get(f"{PUBLIC_BASE}/products/{product_id}")
    if resp.status_code != 200:
        raise CoinbaseError(f"HTTP {resp.status_code} od {PUBLIC_BASE}: {resp.text[:300]}")
    data = resp.json()
    try:
        return {
            "min_market_funds": float(data["min_market_funds"]),
            "base_increment": float(data["base_increment"]),
        }
    except (KeyError, TypeError, ValueError) as err:
        raise CoinbaseError(f"Odgovor nema očekivana polja min_market_funds/base_increment: {data}") from err


def floor_to_increment(quantity: float, increment: float) -> float:
    """Zaokruži NADOLJE na najbliži dopušteni korak - simulira da Coinbase odbija količine koje
    nisu točan višekratnik base_increment (npr. PEPE se mora kupovati u cijelim komadima)."""
    if increment <= 0:
        return quantity
    steps = int(quantity / increment)
    return steps * increment


def test_connection() -> dict:
    """Vraća dijagnostiku - ista konvencija kao /api/tender-search/test-connection u Tender aplikaciji."""
    result = {"public_feed": {"ok": False, "message": ""}}
    try:
        price = get_public_price("BTC-EUR")
        result["public_feed"] = {"ok": True, "message": f"BTC-EUR = {price}"}
    except Exception as err:
        result["public_feed"] = {"ok": False, "message": str(err)}
    return result
