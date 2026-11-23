"""EMA presjek (brzi/spori) uz dugoročni (200-dnevni) trend filter - kupuje samo kad brzi EMA
presijeca spori EMA prema gore I cijena je iznad 200-dnevnog prosjeka, prodaje čim jedan uvjet
otpadne. Port ChatGPT-ovog "ema" kinda iz KriptoMVP 5.1 paralelnog istraživanja (`backtest_51.py`).
Razlikuje se od `technical_composite` (koristi EMA umjesto SMA za presjek, i jednostavniji
jednostruki trend filter umjesto glasovanja više indikatora) - usporedi oba na dashboardu."""
from app.indicators import ema
from app.strategies.base import Decision, StrategyContext


def _sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def decide(ctx: StrategyContext) -> Decision:
    fast_n = int(ctx.params.get("fast", 9))
    slow_n = int(ctx.params.get("slow", 21))
    trend_n = int(ctx.params.get("trend_period", 200))
    closes = [c.close for c in ctx.candles[: ctx.index + 1]]

    if len(closes) < trend_n:
        return "hold"

    fast_ema, slow_ema, trend_ma = ema(closes, fast_n), ema(closes, slow_n), _sma(closes, trend_n)
    if None in (fast_ema, slow_ema, trend_ma):
        return "hold"

    guard_ok = fast_ema > slow_ema and closes[-1] > trend_ma

    if guard_ok and not ctx.in_position:
        return "buy"
    if not guard_ok and ctx.in_position:
        return "sell"
    return "hold"


LABEL = "EMA presjek + 200-dnevni trend filter"
DEFAULT_PARAMS = {"fast": 9, "slow": 21, "trend_period": 200}
