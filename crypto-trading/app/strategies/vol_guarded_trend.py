"""Trend Guard (SMA presjek + 100-dnevni regime filter), uz dodatni uvjet da se NE kupuje kad je
trenutna volatilnost (20-dnevna std. dnevnih prinosa) iznad svog 80. percentila unatrag 180 dana -
ideja je izbjeći ulazak baš u trenutku naglog skoka neizvjesnosti. Port ChatGPT-ovog "volguard"
kinda iz KriptoMVP 5.1 paralelnog istraživanja (`backtest_51.py`)."""
from app.strategies.base import Decision, StrategyContext


def _sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def _vol_at(closes: list[float], end_index: int, window: int) -> float | None:
    """Std. dnevnih prinosa za window dana koji završavaju na closes[end_index] (uključivo)."""
    if end_index - window < 0:
        return None
    rets = [closes[i] / closes[i - 1] - 1 for i in range(end_index - window + 1, end_index + 1)]
    mean = sum(rets) / len(rets)
    variance = sum((r - mean) ** 2 for r in rets) / len(rets)
    return variance**0.5


def _is_high_vol(closes: list[float], vol_window: int, vol_lookback: int, quantile: float) -> bool:
    today_index = len(closes) - 1
    today_vol = _vol_at(closes, today_index, vol_window)
    if today_vol is None:
        return False
    history = [
        v
        for i in range(today_index - vol_lookback, today_index)
        if (v := _vol_at(closes, i, vol_window)) is not None
    ]
    if len(history) < vol_lookback // 2:
        return False
    history.sort()
    idx = min(int(len(history) * quantile), len(history) - 1)
    threshold = history[idx]
    return today_vol > threshold


def decide(ctx: StrategyContext) -> Decision:
    fast_n = int(ctx.params.get("fast", 10))
    slow_n = int(ctx.params.get("slow", 40))
    trend_n = int(ctx.params.get("trend_period", 100))
    vol_window = int(ctx.params.get("vol_window", 20))
    vol_lookback = int(ctx.params.get("vol_lookback", 180))
    vol_quantile = float(ctx.params.get("vol_quantile", 0.8))
    closes = [c.close for c in ctx.candles[: ctx.index + 1]]

    needed = max(slow_n, trend_n, vol_window + vol_lookback)
    if len(closes) < needed:
        return "hold"

    fast_ma, slow_ma, trend_ma = _sma(closes, fast_n), _sma(closes, slow_n), _sma(closes, trend_n)
    if None in (fast_ma, slow_ma, trend_ma):
        return "hold"

    trend_ok = fast_ma > slow_ma and closes[-1] > trend_ma
    high_vol = _is_high_vol(closes, vol_window, vol_lookback, vol_quantile)
    guard_ok = trend_ok and not high_vol

    if guard_ok and not ctx.in_position:
        return "buy"
    if not guard_ok and ctx.in_position:
        return "sell"
    return "hold"


LABEL = "Trend Guard + volatility regime filter"
DEFAULT_PARAMS = {
    "fast": 10,
    "slow": 40,
    "trend_period": 100,
    "vol_window": 20,
    "vol_lookback": 180,
    "vol_quantile": 0.8,
}
