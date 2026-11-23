"""Donchian breakout: kupi kad zatvaranje probije iznad najvišeg maksimuma posljednjih `entry`
dana (PRIJE današnjeg dana - bez gledanja unaprijed), prodaj kad probije ispod najnižeg minimuma
posljednjih `exit` dana. Klasičan trend-praćenje breakout sustav (Turtle Traders), ne mean-reversion.
Port ChatGPT-ovog "donchian" kinda iz KriptoMVP 5.1 paralelnog istraživanja (`backtest_51.py`)."""
from app.strategies.base import Decision, StrategyContext


def decide(ctx: StrategyContext) -> Decision:
    entry_n = int(ctx.params.get("entry_period", 20))
    exit_n = int(ctx.params.get("exit_period", 10))
    candles = ctx.candles[: ctx.index + 1]

    needed = max(entry_n, exit_n) + 1
    if len(candles) < needed:
        return "hold"

    today = candles[-1]
    prior = candles[:-1]  # sve PRIJE današnje svijeće - sprječava gledanje unaprijed

    if not ctx.in_position:
        highest = max(c.high for c in prior[-entry_n:])
        if today.close > highest:
            return "buy"
        return "hold"

    lowest = min(c.low for c in prior[-exit_n:])
    if today.close < lowest:
        return "sell"
    return "hold"


LABEL = "Donchian breakout (probijanje N-dnevnog maksimuma/minimuma)"
DEFAULT_PARAMS = {"entry_period": 20, "exit_period": 10}
