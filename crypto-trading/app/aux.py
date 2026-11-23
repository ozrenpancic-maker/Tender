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
