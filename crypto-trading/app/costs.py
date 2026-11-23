"""Troškovni model identičan priloženom istraživačkom alatu (kripto.py), radi usporedivih backtestova:
0,1% pogoršanje cijene (slippage) i 0,4% naknada po strani (kupnja i prodaja)."""

SLIPPAGE = 0.001
FEE = 0.004


def buy_fill_price(open_price: float) -> float:
    return open_price * (1 + SLIPPAGE)


def sell_fill_price(open_price: float) -> float:
    return open_price * (1 - SLIPPAGE)


def apply_round_trip_cost(gross_multiplier: float) -> float:
    """gross_multiplier = sell_fill / buy_fill, prije naknada."""
    return gross_multiplier * (1 - FEE) / (1 + FEE)
