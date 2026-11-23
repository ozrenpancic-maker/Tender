"""Kupi kad brzi SMA presječe spori SMA prema gore, prodaj kad presječe prema dolje.
Parametri: fast (dana), slow (dana)."""
from app.strategies.base import Decision, StrategyContext


def _sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def decide(ctx: StrategyContext) -> Decision:
    fast_n = int(ctx.params.get("fast", 10))
    slow_n = int(ctx.params.get("slow", 30))
    closes = [c.close for c in ctx.candles[: ctx.index + 1]]

    if len(closes) < slow_n + 1:
        return "hold"

    fast_now, slow_now = _sma(closes, fast_n), _sma(closes, slow_n)
    fast_prev, slow_prev = _sma(closes[:-1], fast_n), _sma(closes[:-1], slow_n)
    if None in (fast_now, slow_now, fast_prev, slow_prev):
        return "hold"

    crossed_up = fast_prev <= slow_prev and fast_now > slow_now
    crossed_down = fast_prev >= slow_prev and fast_now < slow_now

    if crossed_up and not ctx.in_position:
        return "buy"
    if crossed_down and ctx.in_position:
        return "sell"
    return "hold"


LABEL = "SMA presjek (brzi/spori prosjek)"
DEFAULT_PARAMS = {"fast": 10, "slow": 30}
