"""SMA presjek na kriptu, ali 'buy' je dopušten samo kad je S&P 500 (Wall Street) u uzlaznom trendu
(iznad vlastitog N-dnevnog prosjeka) - tzv. risk-on filter. Testira ideju da kripto cijene dobrim
dijelom prate opće raspoloženje na dioničkom tržištu, umjesto da se oslanja samo na kripto cijenu.

Treba 'SPX' u ctx.aux (vidi app.aux i app.equity_client) - ako podatak nije dostupan, strategija se
NE pretvara da zna makro stanje: jednostavno ne kupuje (fail-safe), što će se vidjeti kao niža
aktivnost u rezultatima, ne kao tiho zaobilaženje filtra.
Parametri: fast, slow (kripto SMA), spx_sma (equity SMA period)."""
from app.aux import last_close_on_or_before, sma_on_or_before
from app.strategies.base import Decision, StrategyContext


def _sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def decide(ctx: StrategyContext) -> Decision:
    fast_n = int(ctx.params.get("fast", 10))
    slow_n = int(ctx.params.get("slow", 30))
    spx_sma_n = int(ctx.params.get("spx_sma", 50))
    closes = [c.close for c in ctx.candles[: ctx.index + 1]]

    if len(closes) < slow_n + 1:
        return "hold"

    fast_now, slow_now = _sma(closes, fast_n), _sma(closes, slow_n)
    fast_prev, slow_prev = _sma(closes[:-1], fast_n), _sma(closes[:-1], slow_n)
    if None in (fast_now, slow_now, fast_prev, slow_prev):
        return "hold"

    crossed_up = fast_prev <= slow_prev and fast_now > slow_now
    crossed_down = fast_prev >= slow_prev and fast_now < slow_now

    if crossed_down and ctx.in_position:
        return "sell"

    if crossed_up and not ctx.in_position:
        spx_candles = ctx.aux.get("SPX")
        if not spx_candles:
            return "hold"  # nema makro podatka - ne kupuj naslijepo
        today_ts = ctx.candles[ctx.index].opened_at
        spx_close = last_close_on_or_before(spx_candles, today_ts)
        spx_sma = sma_on_or_before(spx_candles, today_ts, spx_sma_n)
        if spx_close is None or spx_sma is None:
            return "hold"
        if spx_close >= spx_sma:
            return "buy"
        return "hold"  # kripto signal postoji, ali Wall Street je u risk-off trendu

    return "hold"


LABEL = "SMA presjek + S&P 500 risk-on filter"
DEFAULT_PARAMS = {"fast": 10, "slow": 30, "spx_sma": 50}
NEEDS_AUX = ["SPX"]
