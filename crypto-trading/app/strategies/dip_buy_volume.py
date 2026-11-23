"""Kupi nakon pada cijene uz povišen volumen (pokušaj otkupa panike), drži fiksan broj dana, prodaj.
Nadahnuto provjerom iz priloženog xlsx-a (pad >=2% uz volumen >=1.5x prosjeka 20 dana) - ALI ta
provjera sama po sebi NIJE pokazala pozitivnu prednost u priloženim podacima (prosječni pomak nakon
takvog signala bio je približno nula ili negativan). Ova strategija postoji da se to lako testira na
različitim parametrima/razdobljima, ne kao gotova preporuka.
Parametri: drop_pct, volume_mult, lookback, hold_days."""
from app.strategies.base import Decision, StrategyContext


def decide(ctx: StrategyContext) -> Decision:
    drop_pct = float(ctx.params.get("drop_pct", 0.02))
    volume_mult = float(ctx.params.get("volume_mult", 1.5))
    lookback = int(ctx.params.get("lookback", 20))
    hold_days = int(ctx.params.get("hold_days", 3))

    candles = ctx.candles[: ctx.index + 1]
    if len(candles) < lookback + 1:
        return "hold"

    if ctx.in_position:
        entry_index = ctx.params.get("_entry_index")
        if entry_index is not None and ctx.index - entry_index >= hold_days:
            ctx.params["_entry_index"] = None
            return "sell"
        return "hold"

    today = candles[-1]
    past = candles[-1 - lookback : -1]
    avg_volume = sum(c.volume for c in past) / lookback
    move = today.close / past[-1].close - 1

    if move <= -drop_pct and avg_volume and today.volume >= volume_mult * avg_volume:
        ctx.params["_entry_index"] = ctx.index
        return "buy"
    return "hold"


LABEL = "Otkup panike uz volumen (dip-buy)"
DEFAULT_PARAMS = {"drop_pct": 0.02, "volume_mult": 1.5, "lookback": 20, "hold_days": 3}
