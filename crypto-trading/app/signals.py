"""Trenutni (uživo) signal kupi/prodaj po dva horizonta - ne backtest, nego "što bi strategija
odlučila upravo sada" na temelju najnovijih dostupnih svijeća.

VAŽNO - poštena slika onoga što ovo jest:
- Kratkoročni preset (`sma_crossover` fast=12/slow=48, 4h svijeće - u satima ~2 dana/8 dana) NIJE
  "uvijek pobjeđuje" strategija - na jedinom stvarnom testu koji imamo (3,5 mjeseca, BTC/ETH/SOL)
  davao je LOŠIJI rezultat od "kupi i drži" tijekom snažnog uzlaznog trenda, ali je dramatično
  ograničio gubitak tijekom pada (pad od svega nekoliko % umjesto 30%+ za buy&hold). To je svjestan
  kompromis (manje potencijalne dobiti za puno manji rizik), ne dokazana prednost u svim uvjetima.
  Nije testiran na XRP/SUI/PEPE/DOGE - samo na BTC/ETH/SOL. Isto tako, stvarna učestalost trgovanja
  u tom testu bila je otprilike jednom svakih 1-2 tjedna po paru, NE doslovno svakih par sati -
  prave "provjeri svaka 2 sata" konfiguracije (RSI, brzi SMA) su u istom testu izgubile novac zbog
  naknada, pa nisu korištene. "Kratkoročno" ovdje realno znači "brže od dugoročnog", ne "intradan".
  Namjerno je odabrana STATELESS strategija (sma_crossover) umjesto `dip_buy_volume` jer potonja
  pamti kada je "ušla u poziciju" kroz uzastopne pozive u backtestu - za živi signal ne znamo kad si
  ti stvarno kupio pojedini coin, pa bi takav uvjet izlaska bio neupotrebljiv/pogrešan.
- Dugoročni preset (`sma_crossover`, dnevne svijeće, fast=10/slow=40) ima više potpore (testiran na
  4 para kroz puni ciklus 2022-2026, vidi README "Pretraga po više parova"), ali i dalje nije
  testiran na XRP/SUI/PEPE/DOGE/POL/NEAR/ALGO specifično.
- Oba su mehanički signali, ne preporuke financijskog savjetnika. Mogu biti u krivu.

ŽIVI DOHVAT PREKO COINBASE-A, NE BINANCEA (23.11.2026., nakon što je okruženju dopušten izlazni
internet pristup): Binance REST API je geografski blokiran iz ovog okruženja (HTTP 451), Coinbase
nije - i svih 7 korisnikovih portfolio coinova (XRP, SUI, PEPE, DOGE, POL, NEAR, ALGO) su uživo
potvrđeni dostupni na Coinbaseu (XRP-USD, SUI-USD, itd.). Coinbase nema izravnu 4h granulaciju -
za "4h" preset dohvate se 1h svijeće i agregiraju (resample_candles)."""
from app import coinbase_client
from app.candles import resample_candles
from app.strategies import GENERIC_STRATEGIES
from app.strategies.base import StrategyContext

_GRANULARITY = {"4h": 3600, "1d": 86400}  # "4h" dohvaća 1h i resampla - Coinbase nema izravnu 4h

PRESETS = {
    "short": {
        "label": "Kratkoročno (realno: par dana do 1-2 tjedna po trgovini, 4h svijeće)",
        "interval": "4h",
        "lookback_days": 90,
        "strategy": "sma_crossover",
        "params": {"fast": 12, "slow": 48},
        "min_candles": 55,
    },
    "long": {
        "label": "Dugoročno (3+ mjeseca)",
        "interval": "1d",
        "lookback_days": 400,
        "strategy": "sma_crossover",
        "params": {"fast": 10, "slow": 40},
        "min_candles": 45,
    },
}

ACTION_LABELS = {
    ("sell", True): "PRODAJ",
    ("hold", True): "DRŽI",
    ("buy", False): "KUPI",
    ("hold", False): "ČEKAJ",
}


class SignalError(Exception):
    pass


def _fetch_coinbase(pair: str, interval: str, days: int) -> list:
    base = pair.split("/")[0]
    product_id = f"{base}-USD"
    lookback_seconds = days * 86400
    if interval == "4h":
        hourly = coinbase_client.get_public_candles_paginated(product_id, 3600, lookback_seconds)
        return resample_candles(hourly, 60, 240)
    return coinbase_client.get_public_candles_paginated(product_id, _GRANULARITY[interval], lookback_seconds)


def compute_signal(pair: str, horizon: str) -> dict:
    if horizon not in PRESETS:
        raise SignalError(f"Nepoznat horizont '{horizon}'. Dostupno: {list(PRESETS)}")
    preset = PRESETS[horizon]

    candles = _fetch_coinbase(pair, preset["interval"], preset["lookback_days"])
    if len(candles) < preset["min_candles"]:
        raise SignalError(
            f"Nedovoljno svijeća za {pair} ({len(candles)}, treba barem {preset['min_candles']}) - "
            f"par je možda prenov ili simbol nije točan."
        )

    strategy = GENERIC_STRATEGIES[preset["strategy"]]
    params = {**strategy["default_params"], **preset["params"]}
    decide = strategy["decide"]
    last_index = len(candles) - 1

    # Procjena za "trenutno drži" (prava situacija za sve coinove iz portfelja) - bitno je PRODAJ/DRŽI.
    holding_ctx = StrategyContext(candles=candles, index=last_index, in_position=True, params=dict(params), aux={}, series={})
    holding_decision = decide(holding_ctx)

    # Procjena za "trenutno ne drži" (da dokupljuješ/ponovno ulaziš) - bitno je KUPI/ČEKAJ.
    entry_ctx = StrategyContext(candles=candles, index=last_index, in_position=False, params=dict(params), aux={}, series={})
    entry_decision = decide(entry_ctx)

    latest = candles[-1]

    return {
        "pair": pair,
        "horizon": horizon,
        "horizon_label": preset["label"],
        "strategy": preset["strategy"],
        "params": params,
        "price": latest.close,
        "as_of": latest.opened_at,
        "holding_action": ACTION_LABELS.get((holding_decision, True), holding_decision),
        "entry_action": ACTION_LABELS.get((entry_decision, False), entry_decision),
    }


def compute_all(pairs: list[str]) -> dict:
    result = {}
    for pair in pairs:
        result[pair] = {}
        for horizon in PRESETS:
            try:
                result[pair][horizon] = compute_signal(pair, horizon)
            except Exception as err:
                result[pair][horizon] = {"error": str(err)}
    return result
