"""Konfiguracija učitana iz environment varijabli (.env)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("CRYPTO_DB_PATH", ROOT / "data" / "kripto.sqlite"))

# Coinbase Advanced Trade API (CDP API key - par "organizations/.../apiKeys/..." + EC privatni ključ).
# Vidi README.md za upute kako ga napraviti. Bez ovoga rade samo backtest i javni cjenovni feed.
COINBASE_API_KEY_NAME = os.environ.get("COINBASE_API_KEY_NAME", "")
COINBASE_API_PRIVATE_KEY = os.environ.get("COINBASE_API_PRIVATE_KEY", "")  # PEM, s \n za nove retke

# Sigurnosna kočnica: dok god je False, live_engine NIKADA ne šalje prave naloge čak i ako se pokrene.
LIVE_TRADING_ENABLED = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() == "true"

# Postavke rizika za live trgovanje (ignorirano u paper modu, koji uvijek kreće sa 500 virtualnih EUR).
LIVE_MAX_POSITION_EUR = float(os.environ.get("LIVE_MAX_POSITION_EUR", "0"))
LIVE_DAILY_LOSS_LIMIT_EUR = float(os.environ.get("LIVE_DAILY_LOSS_LIMIT_EUR", "0"))

PAPER_STARTING_BALANCE_EUR = float(os.environ.get("PAPER_STARTING_BALANCE_EUR", "500"))
