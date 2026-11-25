"""SMA presjek na kriptu s dva makro filtra za 'buy':
1) S&P 500 iznad svog N-dnevnog prosjeka (risk-on na dioničkom tržištu), I
2) zlato NIJE u naglom skoku iznad svog prosjeka (skok zlata je tipičan znak "bijega u sigurnost",
   tj. risk-off raspoloženja koje obično ide protiv rizičnije imovine poput kriptovaluta).

Oba uvjeta moraju biti ispunjena da se 'buy' signal iskoristi. Ako bilo koji makro podatak
nedostaje, strategija NE kupuje (fail-safe) - radije propušta priliku nego da nagađa.
Parametri: fast, slow, spx_sma, gold_sma, gold_spike_pct."""
from app.aux_candles import last_close_on_or_before, sma_on_or_before
from app.strategies.base import Decision, StrategyContext


def _sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def decide(ctx: StrategyContext) -> Decision:
    fast_n = int(ctx.params.get("fast", 10))
    slow_n = int(ctx.params.get("slow", 30))
    spx_sma_n = int(ctx.params.get("spx_sma", 50))
    gold_sma_n = int(ctx.params.get("gold_sma", 50))
    gold_spike_pct = float(ctx.params.get("gold_spike_pct", 0.05))

    closes = [c.close for c in ctx.candles[: ctx.index + 1]]
    if len(closes) < slow_n + 1:
        return "hold"

    fast_now, slow_now = _sma(closes, fast_n), _sma(closes, slow_n)
    fast_prev, slow_prev = _sma(closes[:-1], fast_n), _sma(closes[:-1], slow_n)
    if None in (fast_now, slow_now, fast_prev, slow_prev):
        return "hold"

    crossed_up = fast_prev <= slow_prev and fast_now > slow_now
    crossed_down = fast_prev >= slow_prev and fast_now < slow_now

    if crossed_down and ctx.in_position:
        return "sell"

    if crossed_up and not ctx.in_position:
        spx_candles, gold_candles = ctx.aux.get("SPX"), ctx.aux.get("GOLD")
        if not spx_candles or not gold_candles:
            return "hold"

        today_ts = ctx.candles[ctx.index].opened_at
        spx_close = last_close_on_or_before(spx_candles, today_ts)
        spx_sma = sma_on_or_before(spx_candles, today_ts, spx_sma_n)
        gold_close = last_close_on_or_before(gold_candles, today_ts)
        gold_sma = sma_on_or_before(gold_candles, today_ts, gold_sma_n)
        if None in (spx_close, spx_sma, gold_close, gold_sma):
            return "hold"

        spx_risk_on = spx_close >= spx_sma
        gold_not_spiking = gold_close <= gold_sma * (1 + gold_spike_pct)

        if spx_risk_on and gold_not_spiking:
            return "buy"
        return "hold"

    return "hold"


LABEL = "SMA presjek + S&P 500 i zlato (dvostruki makro filter)"
DEFAULT_PARAMS = {"fast": 10, "slow": 30, "spx_sma": 50, "gold_sma": 50, "gold_spike_pct": 0.05}
NEEDS_AUX = ["SPX", "GOLD"]
