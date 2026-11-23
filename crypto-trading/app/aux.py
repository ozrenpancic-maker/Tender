"""Pomoćne funkcije za strategije koje koriste dodatne (npr. makro/equity) serije podataka
uz glavni trgovani par."""
from app.candles import Candle


def last_close_on_or_before(candles: list[Candle], ts: int) -> float | None:
    """candles mora biti kronološki sortiran. Koristi se za usklađivanje serija s različitim
    kalendarom trgovanja (npr. burza vikendom ne radi, kripto radi) - uzima zadnju poznatu
    vrijednost na dan ili prije traženog trenutka."""
    result = None
    for c in candles:
        if c.opened_at > ts:
            break
        result = c.close
    return result


def sma_on_or_before(candles: list[Candle], ts: int, period: int) -> float | None:
    closes = [c.close for c in candles if c.opened_at <= ts]
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


# ---- Ravne (ne-OHLC) serije, oblika [(timestamp, value), ...] kronološki sortirano ----
# Koristi se za makro podatke (FRED, DeFiLlama TVL, CoinGecko ponuda, Google Trends, sentiment skor).

SeriesPoint = tuple[int, float]


def series_value_on_or_before(series: list[SeriesPoint], ts: int) -> float | None:
    result = None
    for point_ts, value in series:
        if point_ts > ts:
            break
        result = value
    return result


def series_points_on_or_before(series: list[SeriesPoint], ts: int) -> list[float]:
    return [value for point_ts, value in series if point_ts <= ts]


def series_change_pct(series: list[SeriesPoint], ts: int, lookback_points: int) -> float | None:
    """Postotna promjena zadnje vrijednosti u odnosu na onu `lookback_points` ranije (po broju
    zabilježenih točaka, ne dana - serije poput FRED-a nemaju dnevnu rezoluciju)."""
    points = series_points_on_or_before(series, ts)
    if len(points) <= lookback_points or points[-1 - lookback_points] == 0:
        return None
    base = points[-1 - lookback_points]
    return 100 * (points[-1] - base) / base
