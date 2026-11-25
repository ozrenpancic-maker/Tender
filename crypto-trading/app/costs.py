"""Troškovni model identičan priloženom istraživačkom alatu (kripto.py), radi usporedivih backtestova:
0,1% pogoršanje cijene (slippage) i 0,4% naknada po strani (kupnja i prodaja). Ovo su i dalje
ZADANE ("default") vrijednosti koje svaka funkcija ovdje koristi ako joj se ne proslijedi drugačije.

COST_SCENARIOS (nađeno kao nedostatak u ChatGPT-ovoj neovisnoj reviziji - "realne naknade kao
scenarij, ne fiksna pretpostavka"): nekoliko orijentacijskih scenarija za test osjetljivosti.

NAPOMENA O POUZDANOSTI: brojevi za "coinbase_*" scenarije su orijentacijski, temeljeni na OPĆE
poznatoj strukturi Coinbase cjenika (jeftiniji "Advanced Trade" maker/taker po razinama volumena
nasuprot skupljem "jednostavnom" Buy/Sell sučelju sa spread-om uključenim u cijenu) u trenutku
pisanja koda - NISU uživo provjereni protiv trenutnog Coinbase cjenika (nema pristupa internetu u
ovom razvojnom okruženju). Prije ozbiljnog korištenja provjeri aktualni cjenik na
coinbase.com/advanced-fees i coinbase.com/price/fees."""

SLIPPAGE = 0.001
FEE = 0.004

COST_SCENARIOS = {
    "default": {
        "fee": FEE,
        "slippage": SLIPPAGE,
        "label": "Zadano (0,4% naknada + 0,1% slippage po strani)",
    },
    "coinbase_advanced_low_tier": {
        "fee": 0.006,
        "slippage": 0.0005,
        "label": "Coinbase Advanced Trade, niski volumen (~0,6% taker, orijentacijski)",
    },
    "coinbase_advanced_high_tier": {
        "fee": 0.001,
        "slippage": 0.0003,
        "label": "Coinbase Advanced Trade, visok volumen (~0,1% taker, orijentacijski)",
    },
    "coinbase_simple_app": {
        "fee": 0.0149,
        "slippage": 0.0,
        "label": "Coinbase 'jednostavna' Buy/Sell tipka (~1,49% uključeni spread, orijentacijski)",
    },
    "pessimistic_illiquid": {
        "fee": 0.006,
        "slippage": 0.005,
        "label": "Pesimističan (niska likvidnost, veći slippage na malim/egzotičnim parovima)",
    },
}


def buy_fill_price(open_price: float, slippage: float = SLIPPAGE) -> float:
    return open_price * (1 + slippage)


def sell_fill_price(open_price: float, slippage: float = SLIPPAGE) -> float:
    return open_price * (1 - slippage)


def apply_round_trip_cost(gross_multiplier: float, fee: float = FEE) -> float:
    """gross_multiplier = sell_fill / buy_fill, prije naknada."""
    return gross_multiplier * (1 - fee) / (1 + fee)


# ---------- Uživo izvršenje (bid/ask) - SAMO za paper trading/auto-trader, NE za backtest ----------
# Povijesne OHLC svijeće nemaju bid/ask podatak (samo open/high/low/close/volume) - nema načina
# rekonstruirati stvarni spread unatrag u vremenu bez posebno sakupljenih povijesnih book podataka,
# koje ovaj projekt nema. Ovo je ZATO ograničeno na UŽIVO simulaciju (gdje imamo stvaran trenutni
# bid/ask s Coinbasea), nikad na backtest - vidi README "Realniji troškovni model" za objašnjenje.
#
# MAKER_FEE/TAKER_FEE su ORIJENTACIJSKI (Coinbase Advanced Trade ima razine po 30-dnevnom volumenu,
# promjenjive u vremenu) - NISU uživo provjerene protiv trenutnog cjenika (vidi coinbase.com/
# advanced-fees). Prije ozbiljnog korištenja provjeri aktualne brojke za svoj račun.
TAKER_FEE = 0.006  # niska razina volumena, Coinbase Advanced Trade taker, orijentacijski
MAKER_FEE = 0.004  # niska razina volumena, Coinbase Advanced Trade maker (jeftinije), orijentacijski
RESIDUAL_SLIPPAGE_LIVE = 0.0005  # dodatno kašnjenje odluka->izvršenje, PREKO stvarnog spreada


def taker_buy_fill(ask: float, residual_slippage: float = RESIDUAL_SLIPPAGE_LIVE) -> float:
    """Taker (market) kupnja prelazi spread - plaća se po ask cijeni (ne mid/last), plus malen
    dodatni slippage za ono što spread/dubina knjige JOŠ ne pokriva (kašnjenje mreže/obrade)."""
    return ask * (1 + residual_slippage)


def taker_sell_fill(bid: float, residual_slippage: float = RESIDUAL_SLIPPAGE_LIVE) -> float:
    return bid * (1 - residual_slippage)
