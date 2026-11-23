"""Čisti tehnički indikatori - funkcije primaju listu cijena/svijeća i vraćaju brojeve.
Nema vanjskih poziva, nema stanja; sve je testabilno izolirano od strategija koje ih koriste.
"""
from app.candles import Candle


def sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def ema_series(values: list[float], period: int) -> list[float | None]:
    """Vraća EMA za svaku točku (None dok nema dovoljno povijesti). Prvi EMA se inicijalizira
    kao SMA prvih `period` vrijednosti (uobičajena konvencija)."""
    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return result
    multiplier = 2 / (period + 1)
    seed = sum(values[:period]) / period
    result[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = (values[i] - prev) * multiplier + prev
        result[i] = prev
    return result


def ema(values: list[float], period: int) -> float | None:
    series = ema_series(values, period)
    return series[-1] if series else None


def macd(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[float, float, float] | None:
    """Vraća (macd_line, signal_line, histogram) za zadnju točku, ili None ako nema dovoljno podataka."""
    if len(values) < slow + signal:
        return None
    fast_e = ema_series(values, fast)
    slow_e = ema_series(values, slow)
    macd_line = [f - s if f is not None and s is not None else None for f, s in zip(fast_e, slow_e)]
    valid = [m for m in macd_line if m is not None]
    if len(valid) < signal:
        return None
    signal_series = ema_series(valid, signal)
    signal_value = signal_series[-1]
    if signal_value is None:
        return None
    macd_value = valid[-1]
    return macd_value, signal_value, macd_value - signal_value


def rsi(closes: list[float], period: int = 14) -> float | None:
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


def rsi_series(closes: list[float], period: int = 14) -> list[float | None]:
    return [rsi(closes[: i + 1], period) for i in range(len(closes))]


def stochastic_rsi(closes: list[float], rsi_period: int = 14, stoch_period: int = 14) -> float | None:
    """Vraća %K (0-100). Stoch RSI = (RSI - min(RSI)) / (max(RSI) - min(RSI)) preko stoch_period."""
    series = rsi_series(closes, rsi_period)
    valid = [v for v in series if v is not None]
    if len(valid) < stoch_period:
        return None
    window = valid[-stoch_period:]
    lo, hi = min(window), max(window)
    if hi == lo:
        return 50.0
    return 100 * (window[-1] - lo) / (hi - lo)


def roc(closes: list[float], period: int = 10) -> float | None:
    """Rate of Change u postocima."""
    if len(closes) < period + 1:
        return None
    base = closes[-period - 1]
    if base == 0:
        return None
    return 100 * (closes[-1] - base) / base


def obv_series(candles: list[Candle]) -> list[float]:
    """On Balance Volume - kumulativni pokazatelj: dodaje volumen na dane rasta, oduzima na dane pada."""
    result = [0.0]
    for i in range(1, len(candles)):
        if candles[i].close > candles[i - 1].close:
            result.append(result[-1] + candles[i].volume)
        elif candles[i].close < candles[i - 1].close:
            result.append(result[-1] - candles[i].volume)
        else:
            result.append(result[-1])
    return result


def atr(candles: list[Candle], period: int = 14) -> float | None:
    if len(candles) < period + 1:
        return None
    true_ranges = []
    for i in range(1, len(candles)):
        c = candles[i]
        prev_close = candles[i - 1].close
        tr = max(c.high - c.low, abs(c.high - prev_close), abs(c.low - prev_close))
        true_ranges.append(tr)
    return sum(true_ranges[-period:]) / period


def bollinger_bands(closes: list[float], period: int = 20, num_std: float = 2.0) -> tuple[float, float, float] | None:
    """Vraća (donja, srednja, gornja) vrpca za zadnju točku."""
    if len(closes) < period:
        return None
    window = closes[-period:]
    mean = sum(window) / period
    variance = sum((x - mean) ** 2 for x in window) / period
    std = variance**0.5
    return mean - num_std * std, mean, mean + num_std * std


def bollinger_bandwidth(closes: list[float], period: int = 20, num_std: float = 2.0) -> float | None:
    """Relativna širina vrpci (gornja-donja)/srednja - sužavanje često prethodi velikom pokretu."""
    bands = bollinger_bands(closes, period, num_std)
    if bands is None:
        return None
    lower, mid, upper = bands
    if mid == 0:
        return None
    return (upper - lower) / mid
