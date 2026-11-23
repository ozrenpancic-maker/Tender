"""Isto kao Trend Guard (SMA presjek + 100-dnevni regime filter), ali kupnja čeka da uvjet vrijedi
`confirm` uzastopnih dana prije ulaska (manje lažnih ulazaka na granici presjeka, ali kasniji ulaz).
Prodaja je odmah čim uvjet otpadne (bez potvrde - izlaz treba biti brz). Port ChatGPT-ovog "confirm"
kinda iz KriptoMVP 5.1 paralelnog istraživanja."""
from app.strategies.base import Decision, StrategyContext


def _sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def _guard_condition(closes: list[float], fast_n: int, slow_n: int, trend_n: int) -> bool | None:
    fast_ma, slow_ma, trend_ma = _sma(closes, fast_n), _sma(closes, slow_n), _sma(closes, trend_n)
    if None in (fast_ma, slow_ma, trend_ma):
        return None
    return fast_ma > slow_ma and closes[-1] > trend_ma


def decide(ctx: StrategyContext) -> Decision:
    fast_n = int(ctx.params.get("fast", 10))
    slow_n = int(ctx.params.get("slow", 40))
    trend_n = int(ctx.params.get("trend_period", 100))
    confirm_n = int(ctx.params.get("confirm", 3))
    closes = [c.close for c in ctx.candles[: ctx.index + 1]]

    needed = max(slow_n, trend_n) + confirm_n
    if len(closes) < needed:
        return "hold"

    current = _guard_condition(closes, fast_n, slow_n, trend_n)
    if current is None:
        return "hold"

    if not current:
        if ctx.in_position:
            return "sell"
        return "hold"

    if ctx.in_position:
        return "hold"

    confirmed = all(
        _guard_condition(closes[: len(closes) - i], fast_n, slow_n, trend_n) for i in range(confirm_n)
    )
    if confirmed:
        return "buy"
    return "hold"


LABEL = "Potvrđeni Trend Guard (N uzastopnih dana prije ulaska)"
DEFAULT_PARAMS = {"fast": 10, "slow": 40, "trend_period": 100, "confirm": 3}
