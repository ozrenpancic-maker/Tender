"""Kupi kad je funding rate ekstremno negativan (shortovi plaćaju longovima za održavanje pozicije -
znak da je tržište pretrpano shortovima, što je klasičan "short squeeze" predznak), drži fiksan broj
dana, prodaj. Izađi ranije ako funding rate skoči na ekstremno pozitivan (sad pretrpano longovima -
rizik od "long squeeze" pada). Iz korisnikovog popisa: "vrlo važan alat za short squeeze, long
squeeze, detekciju pregrijanog tržišta".

Ovo je kontrarijanski/reversal signal, za razliku od trend-prateećih strategija (sma_crossover,
technical_composite) - testira drukčiju tezu, ne nadogradnju iste.

Ako podatak o funding rateu nedostaje za taj dan, strategija ne kupuje (fail-safe).
Parametri: extreme_negative, extreme_positive, lookback_days, hold_days."""
from app.aux_candles import series_points_on_or_before
from app.strategies.base import Decision, StrategyContext

FUNDING_SERIES_KEY = "BTC_FUNDING"


def decide(ctx: StrategyContext) -> Decision:
    extreme_negative = float(ctx.params.get("extreme_negative", -0.0005))
    extreme_positive = float(ctx.params.get("extreme_positive", 0.0005))
    lookback_days = int(ctx.params.get("lookback_days", 3))
    hold_days = int(ctx.params.get("hold_days", 5))

    funding_series = ctx.series.get(FUNDING_SERIES_KEY)
    if not funding_series:
        return "hold"

    today_ts = ctx.candles[ctx.index].opened_at
    recent_values = series_points_on_or_before(funding_series, today_ts)
    if len(recent_values) < lookback_days:
        return "hold"
    avg_funding = sum(recent_values[-lookback_days:]) / lookback_days

    if ctx.in_position:
        entry_index = ctx.params.get("_entry_index")
        if avg_funding >= extreme_positive:
            ctx.params["_entry_index"] = None
            return "sell"  # tržište se okrenulo na pretrpano longova - izađi ranije
        if entry_index is not None and ctx.index - entry_index >= hold_days:
            ctx.params["_entry_index"] = None
            return "sell"
        return "hold"

    if avg_funding <= extreme_negative:
        ctx.params["_entry_index"] = ctx.index
        return "buy"
    return "hold"


LABEL = "Derivati - funding rate ekstremi (short/long squeeze)"
DEFAULT_PARAMS = {"extreme_negative": -0.0005, "extreme_positive": 0.0005, "lookback_days": 3, "hold_days": 5}
NEEDS_SERIES = [{"source": "binance_futures", "series_id": FUNDING_SERIES_KEY}]
