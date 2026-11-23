"""DeFiLlama - besplatan, javni API bez ključa za TVL (Total Value Locked) po blockchainu/protokolu.
Koristi se kao fundamentalni "korištenje mreže" signal za altcoine (rast TVL-a = više kapitala
zaključano u DeFi na toj mreži).

UŽIVO TESTIRANO (23.11.2026., nakon što je okruženju dopušten izlazni internet pristup) - radi."""
import time

import httpx

DEFILLAMA_BASE = "https://api.llama.fi"

# Oznaka -> DeFiLlama chain slug.
CHAINS = {
    "ETHEREUM_TVL": "Ethereum",
    "SOLANA_TVL": "Solana",
}


class DefiLlamaError(Exception):
    pass


def _fetch_chain_tvl(chain_slug: str) -> list[dict]:
    with httpx.Client(timeout=20) as client:
        resp = client.get(f"{DEFILLAMA_BASE}/v2/historicalChainTvl/{chain_slug}")
    if resp.status_code != 200:
        raise DefiLlamaError(f"HTTP {resp.status_code} od DeFiLlama za {chain_slug}: {resp.text[:300]}")
    data = resp.json()
    if not isinstance(data, list):
        raise DefiLlamaError(f"Neočekivan DeFiLlama odgovor za {chain_slug}: {str(data)[:300]}")
    return data


def fetch_recent(label: str, days: int = 400) -> list[tuple[int, float]]:
    chain_slug = CHAINS.get(label, label)
    data = _fetch_chain_tvl(chain_slug)
    cutoff = time.time() - days * 86400
    points = [(int(row["date"]), float(row["tvl"])) for row in data if int(row["date"]) >= cutoff]
    points.sort()
    return points


def sync_to_db(conn, label: str) -> int:
    import datetime

    from app.macro_store import save_series

    chain_slug = CHAINS.get(label, label)
    data = _fetch_chain_tvl(chain_slug)
    points = [
        (datetime.datetime.fromtimestamp(int(row["date"]), datetime.timezone.utc).strftime("%Y-%m-%d"), float(row["tvl"]))
        for row in data
    ]
    return save_series(conn, "defillama", label, points)


def test_connection() -> dict:
    result = {}
    for label in CHAINS:
        try:
            points = fetch_recent(label, days=30)
            result[label] = {"ok": True, "message": f"{len(points)} točaka, zadnji TVL: {points[-1][1] if points else '?'}"}
        except Exception as err:
            result[label] = {"ok": False, "message": str(err)}
    return result
