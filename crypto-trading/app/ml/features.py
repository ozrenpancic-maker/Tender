"""Značajke (features) za ML prediction engine - računaju se u JEDNOM prolazu kroz niz svijeća
(ne pozivaju postojeće app/indicators.py funkcije po svakom indeksu, jer su one O(n) po pozivu
i bi dale O(n^2)/O(n^3) ukupno na dužim nizovima). Svaka vrijednost na indeksu i koristi ISKLJUČIVO
svijeće[0..i] - nema gledanja unaprijed (look-ahead).

Vraća listu rječnika, jedan po svijeći, s `None` dok nema dovoljno povijesti za pojedinu značajku -
dataset.py izbacuje redove koji imaju bilo koji `None` prije treniranja.
"""
from app.candles import Candle
from app.indicators import ema_series

FEATURE_NAMES = [
    "rsi14",
    "stoch_rsi14",
    "macd_hist_norm",
    "ema9_dist",
    "ema21_dist",
    "ema50_dist",
    "ema200_dist",
    "sma20_dist",
    "sma50_dist",
    "sma200_dist",
    "atr14_norm",
    "atr_percentile100",
    "bb_pct_b",
    "bb_bandwidth",
    "roc5",
    "roc10",
    "roc20",
    "volume_rel20",
    "dist_from_high20",
    "dist_from_low20",
]


def _rolling_sma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    running = 0.0
    for i, v in enumerate(values):
        running += v
        if i >= period:
            running -= values[i - period]
        if i >= period - 1:
            out[i] = running / period
    return out


def _rolling_std(values: list[float], period: int, means: list[float | None]) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    for i in range(len(values)):
        if means[i] is None:
            continue
        window = values[i - period + 1 : i + 1]
        mean = means[i]
        variance = sum((x - mean) ** 2 for x in window) / period
        out[i] = variance**0.5
    return out


def _rsi_series(closes: list[float], period: int = 14) -> list[float | None]:
    """Wilder's RSI, jedan prolaz O(n)."""
    out: list[float | None] = [None] * len(closes)
    if len(closes) < period + 1:
        return out
    gains = losses = 0.0
    for i in range(1, period + 1):
        change = closes[i] - closes[i - 1]
        if change >= 0:
            gains += change
        else:
            losses -= change
    avg_gain, avg_loss = gains / period, losses / period
    out[period] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    for i in range(period + 1, len(closes)):
        change = closes[i] - closes[i - 1]
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out[i] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    return out


def _stoch_rsi_series(rsi_vals: list[float | None], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(rsi_vals)
    for i in range(len(rsi_vals)):
        if rsi_vals[i] is None:
            continue
        window = [v for v in rsi_vals[max(0, i - period + 1) : i + 1] if v is not None]
        if len(window) < period:
            continue
        lo, hi = min(window), max(window)
        out[i] = 50.0 if hi == lo else 100 * (window[-1] - lo) / (hi - lo)
    return out


def _atr_series(candles: list[Candle], period: int = 14) -> list[float | None]:
    """Wilder's ATR, jedan prolaz O(n)."""
    out: list[float | None] = [None] * len(candles)
    if len(candles) < period + 1:
        return out
    trs = []
    for i in range(1, len(candles)):
        c, prev_close = candles[i], candles[i - 1].close
        trs.append(max(c.high - c.low, abs(c.high - prev_close), abs(c.low - prev_close)))
    atr_val = sum(trs[:period]) / period
    out[period] = atr_val
    for i in range(period, len(trs)):
        atr_val = (atr_val * (period - 1) + trs[i]) / period
        out[i + 1] = atr_val
    return out


def _percentile_rank(values: list[float | None], window: int) -> list[float | None]:
    """Gdje je trenutna vrijednost (0-100) unutar svoje posljednje `window` povijesti - koristi se
    za 'volatility percentile' (ATR danas vs ATR posljednjih ~100 svijeća)."""
    out: list[float | None] = [None] * len(values)
    for i in range(len(values)):
        if values[i] is None:
            continue
        lookback = [v for v in values[max(0, i - window + 1) : i + 1] if v is not None]
        if len(lookback) < min(window, 30):
            continue
        rank = sum(1 for v in lookback if v <= values[i])
        out[i] = 100 * rank / len(lookback)
    return out


def _roc_series(closes: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    for i in range(period, len(closes)):
        base = closes[i - period]
        if base:
            out[i] = 100 * (closes[i] - base) / base
    return out


def compute_feature_frame(candles: list[Candle]) -> list[dict]:
    """Vraća listu rječnika (po jedan po svijeći), svaka značajka koristi samo candles[0..i]."""
    closes = [c.close for c in candles]
    volumes = [c.volume for c in candles]
    n = len(candles)

    ema9 = ema_series(closes, 9)
    ema21 = ema_series(closes, 21)
    ema50 = ema_series(closes, 50)
    ema200 = ema_series(closes, 200)
    macd_fast = ema_series(closes, 12)
    macd_slow = ema_series(closes, 26)
    macd_line = [f - s if f is not None and s is not None else None for f, s in zip(macd_fast, macd_slow)]
    valid_macd = [m for m in macd_line if m is not None]
    macd_signal_valid = ema_series(valid_macd, 9) if len(valid_macd) >= 9 else []
    # Poravnaj signalnu liniju natrag na puni indeks (macd_line ima None na početku).
    macd_signal: list[float | None] = [None] * n
    offset = n - len(valid_macd)
    for j, v in enumerate(macd_signal_valid):
        macd_signal[offset + j] = v

    sma20 = _rolling_sma(closes, 20)
    sma50 = _rolling_sma(closes, 50)
    sma200 = _rolling_sma(closes, 200)
    bb_mean = sma20
    bb_std = _rolling_std(closes, 20, bb_mean)

    rsi14 = _rsi_series(closes, 14)
    stoch_rsi14 = _stoch_rsi_series(rsi14, 14)
    atr14 = _atr_series(candles, 14)
    atr_pct = _percentile_rank(atr14, 100)
    vol_sma20 = _rolling_sma(volumes, 20)
    roc5 = _roc_series(closes, 5)
    roc10 = _roc_series(closes, 10)
    roc20 = _roc_series(closes, 20)

    rows = []
    for i in range(n):
        close = closes[i]
        row: dict = {}
        row["rsi14"] = rsi14[i]
        row["stoch_rsi14"] = stoch_rsi14[i]
        row["macd_hist_norm"] = (
            (macd_line[i] - macd_signal[i]) / close
            if macd_line[i] is not None and macd_signal[i] is not None and close
            else None
        )
        row["ema9_dist"] = (close / ema9[i] - 1) if ema9[i] else None
        row["ema21_dist"] = (close / ema21[i] - 1) if ema21[i] else None
        row["ema50_dist"] = (close / ema50[i] - 1) if ema50[i] else None
        row["ema200_dist"] = (close / ema200[i] - 1) if ema200[i] else None
        row["sma20_dist"] = (close / sma20[i] - 1) if sma20[i] else None
        row["sma50_dist"] = (close / sma50[i] - 1) if sma50[i] else None
        row["sma200_dist"] = (close / sma200[i] - 1) if sma200[i] else None
        row["atr14_norm"] = (atr14[i] / close) if atr14[i] is not None and close else None
        row["atr_percentile100"] = atr_pct[i]
        if bb_mean[i] is not None and bb_std[i] is not None and bb_std[i] > 0:
            lower, upper = bb_mean[i] - 2 * bb_std[i], bb_mean[i] + 2 * bb_std[i]
            row["bb_pct_b"] = (close - lower) / (upper - lower)
            row["bb_bandwidth"] = (upper - lower) / bb_mean[i]
        else:
            row["bb_pct_b"] = None
            row["bb_bandwidth"] = None
        row["roc5"] = roc5[i]
        row["roc10"] = roc10[i]
        row["roc20"] = roc20[i]
        row["volume_rel20"] = (volumes[i] / vol_sma20[i] - 1) if vol_sma20[i] else None
        window20 = candles[max(0, i - 19) : i + 1]
        if len(window20) == 20:
            high20, low20 = max(c.high for c in window20), min(c.low for c in window20)
            row["dist_from_high20"] = (close / high20 - 1) if high20 else None
            row["dist_from_low20"] = (close / low20 - 1) if low20 else None
        else:
            row["dist_from_high20"] = None
            row["dist_from_low20"] = None
        rows.append(row)
    return rows
