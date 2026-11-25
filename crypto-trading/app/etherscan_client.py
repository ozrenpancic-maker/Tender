"""Etherscan - javni, dokumentirani, besplatan API (5 poziva/s na free tieru) za ETH on-chain
podatke. Koristi se za "whale mirror" (app/whale_mirror.py): zrcali promjene stanja JAVNOG
novčanika (balans u lančanom registru je po definiciji javan - nema privatnosti za narušiti).

UŽIVO TESTIRANO (25.11.2026., s korisnikovim besplatnim ključem): balance i txlist pozivi rade
normalno iz ovog sandbox okruženja (za razliku od Binance/CoinGecko/FRED/Reddit, Etherscan v2 API
NIJE blokiran odavde).

NAPOMENA: ovo je Etherscan API v2 (v1 je deprecated, traži migraciju na v2 s `chainid` parametrom -
vidi docs.etherscan.io/v2-migration). chainid=1 = Ethereum mainnet.
"""
import time

import httpx

from app.config import ETHERSCAN_API_KEY

ETHERSCAN_BASE = "https://api.etherscan.io/v2/api"
CHAIN_ID_ETHEREUM = 1


class EtherscanError(Exception):
    pass


def _get(params: dict) -> dict:
    if not ETHERSCAN_API_KEY:
        raise EtherscanError("ETHERSCAN_API_KEY nije postavljen u .env (besplatna registracija: etherscan.io/apis).")
    params = {**params, "chainid": CHAIN_ID_ETHEREUM, "apikey": ETHERSCAN_API_KEY}
    try:
        resp = httpx.get(ETHERSCAN_BASE, params=params, timeout=15)
        resp.raise_for_status()
    except httpx.HTTPError as err:
        raise EtherscanError(f"Etherscan zahtjev nije uspio: {err}") from err
    data = resp.json()
    if data.get("status") != "1":
        message = data.get("message", "nepoznata greška")
        result = data.get("result", "")
        # "No transactions found" dolazi s status=0 ali NIJE stvarna greška (prazan rezultat je ispravan).
        if message == "No transactions found":
            return data
        raise EtherscanError(f"Etherscan: {message} ({result})")
    return data


def get_eth_balance(address: str) -> float:
    """Trenutno ETH stanje javne adrese (ne wei - pretvoreno u ETH)."""
    data = _get({"module": "account", "action": "balance", "address": address, "tag": "latest"})
    return int(data["result"]) / 1e18


def get_recent_transactions(address: str, limit: int = 5) -> list[dict]:
    """Zadnjih N transakcija (najnovije prvo) - samo za prikaz u dashboardu (transparentnost: "zašto
    je ovaj trade izvršen"), ne koristi se za samu odluku (ta se temelji na balance-delti)."""
    data = _get(
        {
            "module": "account", "action": "txlist", "address": address,
            "startblock": 0, "endblock": 99999999, "page": 1, "offset": limit, "sort": "desc",
        }
    )
    out = []
    for tx in data.get("result", []):
        if not isinstance(tx, dict):
            continue
        out.append(
            {
                "at": int(tx["timeStamp"]),
                "value_eth": int(tx["value"]) / 1e18,
                "direction": "in" if tx["to"].lower() == address.lower() else "out",
                "from": tx["from"],
                "to": tx["to"],
                "hash": tx["hash"],
            }
        )
    return out


def test_connection() -> dict:
    """Za dashboard 'Testiraj vezu' gumb - koristi poznatu javnu adresu (Ethereum Foundation)."""
    address = "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe"
    started = time.monotonic()
    balance = get_eth_balance(address)
    elapsed_ms = round((time.monotonic() - started) * 1000)
    return {"ok": True, "elapsed_ms": elapsed_ms, "sample_address": address, "sample_balance_eth": round(balance, 4)}
