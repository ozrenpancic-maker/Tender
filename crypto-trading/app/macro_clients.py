"""Registar svih makro/sentiment/fundamentalnih klijenata - svaki modul izlaže:
fetch_recent(label, days) -> list[(timestamp, value)], sync_to_db(conn, label) -> int, test_connection() -> dict.
"""
from app import coingecko_client, defillama_client, etf_client, fred_client, reddit_client, regulatory_client, trends_client

MACRO_CLIENTS = {
    "fred": fred_client,
    "defillama": defillama_client,
    "coingecko": coingecko_client,
    "google_trends": trends_client,
    "reddit": reddit_client,
    "etf_flow": etf_client,
    "regulatory": regulatory_client,
}


def all_labels() -> dict[str, list[str]]:
    return {source: list(getattr(module, _LABELS_ATTR[source])) for source, module in MACRO_CLIENTS.items()}


_LABELS_ATTR = {
    "fred": "SERIES",
    "defillama": "CHAINS",
    "coingecko": "COINS",
    "google_trends": "KEYWORDS",
    "reddit": "SUBREDDITS",
    "etf_flow": "FARSIDE_URLS",
    "regulatory": "FEEDS",
}


def test_all_connections() -> dict:
    return {source: module.test_connection() for source, module in MACRO_CLIENTS.items()}
