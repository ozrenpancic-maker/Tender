"""Konfiguracija učitana iz environment varijabli (.env)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")  # .env sam po sebi nije automatski učitan ni od uvicorna ni od Pythona

DB_PATH = Path(os.environ.get("CRYPTO_DB_PATH", ROOT / "data" / "kripto.sqlite"))

# NAPOMENA (KriptoMVP 4.4 nepromjenjiva pravila): aplikacija je isključivo savjetnik/simulator.
# Namjerno NEMA konfiguracije za Coinbase trgovačke (autenticirane) API ključeve niti za slanje
# pravih naloga - taj kod je uklonjen (vidi git povijest `live_engine.py` ako ga treba za referencu).
# Koristi se samo javni, read-only Coinbase cjenovni feed (bez ključa).

PAPER_STARTING_BALANCE_EUR = float(os.environ.get("PAPER_STARTING_BALANCE_EUR", "500"))

# Opcionalni API ključ za dashboard (nađeno u ChatGPT-ovoj neovisnoj reviziji: API nije imao NIKAKVU
# autentikaciju - u redu za localhost, rizično ako server postane dostupan izvan vlastitog računala
# npr. port forwarding). Ako je postavljen, svi /api/* pozivi moraju slati
# "Authorization: Bearer <ključ>" header. Ako NIJE postavljen (default), ponašanje je nepromijenjeno
# - i dalje misliš da je ovo za kućnu/uredsku WiFi mrežu, ne javni internet (vidi README).
DASHBOARD_API_KEY = os.environ.get("DASHBOARD_API_KEY", "")

# FRED (Federal Reserve Economic Data) - besplatan ključ: fred.stlouisfed.org/docs/api/api_key.html
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")

# Reddit OAuth2 (client credentials) - besplatna registracija aplikacije: reddit.com/prefs/apps
REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")

# GitHub - opcionalno; bez tokena 60 zahtjeva/sat, s besplatnim Personal Access Tokenom 5000/sat.
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# CryptoPanic - besplatan tier, registracija: cryptopanic.com/developers/api/
CRYPTOPANIC_API_KEY = os.environ.get("CRYPTOPANIC_API_KEY", "")

# Etherscan - besplatan tier (5 poziva/s), registracija: etherscan.io/apis
ETHERSCAN_API_KEY = os.environ.get("ETHERSCAN_API_KEY", "")
