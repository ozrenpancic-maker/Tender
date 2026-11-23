"""RSI mean-reversion: kupi kad je RSI ispod buy_below (prekupljenost/preprodanost - ovdje ulaz na
preprodanost), prodaj kad RSI prijeđe iznad sell_above. Parametri: period, buy_below, sell_above."""
from app.strategies.base import Decision, StrategyContext


def _rsi(closes: list[float], period: int) -> float | None:
    if len(closes) < period + 1:
        return None
    gains = losses = 0.0
    for i in range(-period, 0):
        change = closes[i] - closes[i - 1]
        if change >= 0:
            gains += change
        else:
            losses -= change
    avg_gain, avg_loss = gains / period, losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def decide(ctx: StrategyContext) -> Decision:
    period = int(ctx.params.get("period", 14))
    buy_below = float(ctx.params.get("buy_below", 30))
    sell_above = float(ctx.params.get("sell_above", 60))
    closes = [c.close for c in ctx.candles[: ctx.index + 1]]

    rsi = _rsi(closes, period)
    if rsi is None:
        return "hold"

    if rsi < buy_below and not ctx.in_position:
        return "buy"
    if rsi > sell_above and ctx.in_position:
        return "sell"
    return "hold"


LABEL = "RSI mean-reversion"
DEFAULT_PARAMS = {"period": 14, "buy_below": 30, "sell_above": 60}
