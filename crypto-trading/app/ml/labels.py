"""Label (ciljna klasa) konstrukcija po horizontu - 3 klase: up / down / sideways.

Granica između klasa NIJE fiksni postotak - uzima u obzir:
1. Očekivani trošak jednog round-trip-a (kupnja+prodaja, naknade+slippage iz app/costs.py) - pokret
   manji od ovoga je besmislen za trgovanje čak i da je smjer točno pogođen.
2. Trenutnu volatilnost (ATR, skalirano s korijenom broja koraka unaprijed - standardna
   pretpostavka slučajnog hoda) - "sideways" zona je širа kad je tržište volatilnije, uža kad je
   mirno, umjesto jednog fiksnog broja za sve uvjete i horizonte.

Label na indeksu i koristi ISKLJUČIVO candles[i + steps_ahead].close (budući podatak) - to je
namjerno jedino mjesto u cijelom pipelineu gdje se gleda unaprijed, i mora ostati odvojeno od
features.py (koji gleda samo unatrag) da se spriječi curenje podataka u značajke.
"""
from app.candles import Candle
from app.costs import FEE, SLIPPAGE

ROUND_TRIP_COST = 2 * FEE + 2 * SLIPPAGE  # ~1.0% - fiksni pod iz naknada/slippagea
VOLATILITY_MULTIPLIER = 0.5  # koliko ATR-a (skalirano s horizontom) čini "sideways" zonu

UP, DOWN, SIDEWAYS = "up", "down", "sideways"


def label_series(candles: list[Candle], steps_ahead: int, atr14_norm: list[float | None]) -> list[str | None]:
    """Vraća listu labela iste dužine kao candles; `None` na zadnjih `steps_ahead` indeksa
    (nema budućeg podatka) i gdje ATR još nije dostupan."""
    n = len(candles)
    out: list[str | None] = [None] * n
    for i in range(n - steps_ahead):
        if atr14_norm[i] is None:
            continue
        base = candles[i].close
        if not base:
            continue
        forward_return = (candles[i + steps_ahead].close - base) / base
        threshold = max(ROUND_TRIP_COST, VOLATILITY_MULTIPLIER * atr14_norm[i] * steps_ahead**0.5)
        if forward_return > threshold:
            out[i] = UP
        elif forward_return < -threshold:
            out[i] = DOWN
        else:
            out[i] = SIDEWAYS
    return out
