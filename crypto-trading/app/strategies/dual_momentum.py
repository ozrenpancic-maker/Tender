"""Dual momentum: kupi kad je cijena iznad dugoročnog (200-dnevnog) trenda I zabilježila momentum
(promjena cijene unatrag `momentum_period` dana) iznad praga; prodaj kad padne ispod kratkog
(`exit_period`-dnevnog) prosjeka ILI momentum padne ispod -praga. Port ChatGPT-ovog "dual" kinda iz
KriptoMVP 5.1 paralelnog istraživanja (`backtest_51.py`)."""
from app.strategies.base import Decision, StrategyContext


def _sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def decide(ctx: StrategyContext) -> Decision:
    momentum_n = int(ctx.params.get("momentum_period", 60))
    exit_n = int(ctx.params.get("exit_period", 20))
    trend_n = int(ctx.params.get("trend_period", 200))
    threshold = float(ctx.params.get("threshold", 0.0))
    closes = [c.close for c in ctx.candles[: ctx.index + 1]]

    needed = max(momentum_n, exit_n, trend_n) + 1
    if len(closes) < needed:
        return "hold"

    trend_ma, exit_ma = _sma(closes, trend_n), _sma(closes, exit_n)
    if None in (trend_ma, exit_ma):
        return "hold"

    momentum = closes[-1] / closes[-1 - momentum_n] - 1

    if not ctx.in_position:
        if closes[-1] > trend_ma and momentum > threshold:
            return "buy"
        return "hold"

    if closes[-1] < exit_ma or momentum < -threshold:
        return "sell"
    return "hold"


LABEL = "Dual momentum (dugoročni trend + kratkoročni zamah)"
DEFAULT_PARAMS = {"momentum_period": 60, "exit_period": 20, "trend_period": 200, "threshold": 0.0}
