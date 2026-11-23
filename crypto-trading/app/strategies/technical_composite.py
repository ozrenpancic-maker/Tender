"""Kombinira više klasičnih tehničkih signala umjesto oslanjanja na jedan:
- EMA200 trend filter: trguje se SAMO u smjeru dugoročnog trenda (iznad = dopušten buy, ispod = izlaz).
- MACD presjek: ulaz na bullish MACD crossover (MACD linija prijeđe signalnu prema gore).
- OBV potvrda (opcionalno): zahtijeva da je volumen (On Balance Volume) također rastao u zadnjih
  N dana - "rast cijene bez volumena je moguća zamka" (iz korisnikovog popisa čimbenika).

Izlaz: MACD bearish crossover ILI cijena padne ispod EMA200 (što prije nastupi).
Parametri: ema_trend, macd_fast, macd_slow, macd_signal, obv_lookback, require_obv_confirm."""
from app import indicators as ind
from app.strategies.base import Decision, StrategyContext


def decide(ctx: StrategyContext) -> Decision:
    ema_trend_n = int(ctx.params.get("ema_trend", 200))
    macd_fast = int(ctx.params.get("macd_fast", 12))
    macd_slow = int(ctx.params.get("macd_slow", 26))
    macd_signal_n = int(ctx.params.get("macd_signal", 9))
    obv_lookback = int(ctx.params.get("obv_lookback", 10))
    require_obv_confirm = bool(ctx.params.get("require_obv_confirm", True))

    candles = ctx.candles[: ctx.index + 1]
    closes = [c.close for c in candles]

    if len(closes) < max(ema_trend_n, macd_slow + macd_signal_n) + 2:
        return "hold"

    ema_trend_now = ind.ema(closes, ema_trend_n)
    macd_now = ind.macd(closes, macd_fast, macd_slow, macd_signal_n)
    macd_prev = ind.macd(closes[:-1], macd_fast, macd_slow, macd_signal_n)
    if ema_trend_now is None or macd_now is None or macd_prev is None:
        return "hold"

    price = closes[-1]
    above_trend = price > ema_trend_now

    macd_line_now, signal_now, _ = macd_now
    macd_line_prev, signal_prev, _ = macd_prev
    bullish_cross = macd_line_prev <= signal_prev and macd_line_now > signal_now
    bearish_cross = macd_line_prev >= signal_prev and macd_line_now < signal_now

    if ctx.in_position:
        if bearish_cross or not above_trend:
            return "sell"
        return "hold"

    if bullish_cross and above_trend:
        if require_obv_confirm:
            obv = ind.obv_series(candles)
            if len(obv) <= obv_lookback or obv[-1] <= obv[-1 - obv_lookback]:
                return "hold"  # cijena bi mogla rasti, ali volumen ne potvrđuje - moguća zamka
        return "buy"

    return "hold"


LABEL = "Tehnički kompozit (EMA200 trend + MACD + OBV potvrda)"
DEFAULT_PARAMS = {
    "ema_trend": 200,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "obv_lookback": 10,
    "require_obv_confirm": True,
}
