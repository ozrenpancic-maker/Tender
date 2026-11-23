"""Glasovanje više međusobno povezanih čimbenika, u duhu korisnikovog popisa: cilj nije predvidjeti
budućnost sa 100% točnošću, nego procijeniti je li ukupno okruženje 'risk-on' prije nego se uopće
razmotri tehnički ulazni signal.

Obavezan preduvjet (gate, ne glas): cijena mora biti iznad EMA200 - bez toga se ne kupuje, bez obzira
na glasove (isti princip kao technical_composite).

Glasovi (svaki 0 ili 1, "risk-on"):
1. FED stopa ne raste (FEDFUNDS nije porastao u zadnja `fed_lookback` očitanja) - rastuće stope su
   povijesno negativne za rizičnu imovinu.
2. Reddit sentiment (r/CryptoCurrency) >= reddit_threshold.
3. Regulatorni skor (SEC RSS, leksikon) >= regulatory_threshold.
4. Neto ETF tok (BTC) >= etf_threshold (priljev, ne odljev).

Kupnja se dogodi samo ako je iznad EMA200 I broj risk-on glasova >= min_risk_on_votes. Ako neki
podatak nedostaje za taj dan, taj glas se jednostavno ne broji (ne pretvara se u "risk-on" niti
"risk-off" nagađanjem) - manje dostupnih glasova znači da treba više preostalih da prijeđe prag.
Parametri: ema_trend, min_risk_on_votes, fed_lookback, reddit_threshold, regulatory_threshold,
etf_threshold."""
from app import indicators as ind
from app.aux import series_change_pct, series_value_on_or_before
from app.strategies.base import Decision, StrategyContext

NEEDS_SERIES = [
    {"source": "fred", "series_id": "FEDFUNDS"},
    {"source": "reddit", "series_id": "REDDIT_CRYPTO"},
    {"source": "regulatory", "series_id": "REG_SEC"},
    {"source": "etf_flow", "series_id": "BTC_ETF_FLOW"},
]


def decide(ctx: StrategyContext) -> Decision:
    ema_trend_n = int(ctx.params.get("ema_trend", 200))
    min_votes = int(ctx.params.get("min_risk_on_votes", 3))
    fed_lookback = int(ctx.params.get("fed_lookback", 3))
    reddit_threshold = float(ctx.params.get("reddit_threshold", 0.0))
    regulatory_threshold = float(ctx.params.get("regulatory_threshold", 0.0))
    etf_threshold = float(ctx.params.get("etf_threshold", 0.0))

    candles = ctx.candles[: ctx.index + 1]
    closes = [c.close for c in candles]
    if len(closes) < ema_trend_n + 1:
        return "hold"

    ema_trend_now = ind.ema(closes, ema_trend_n)
    if ema_trend_now is None:
        return "hold"

    above_trend = closes[-1] > ema_trend_now
    today_ts = candles[-1].opened_at

    if ctx.in_position:
        return "sell" if not above_trend else "hold"

    if not above_trend:
        return "hold"

    votes = 0
    fed_series = ctx.series.get("FEDFUNDS")
    if fed_series:
        fed_change = series_change_pct(fed_series, today_ts, fed_lookback)
        if fed_change is not None and fed_change <= 0:
            votes += 1

    reddit_series = ctx.series.get("REDDIT_CRYPTO")
    if reddit_series:
        value = series_value_on_or_before(reddit_series, today_ts)
        if value is not None and value >= reddit_threshold:
            votes += 1

    reg_series = ctx.series.get("REG_SEC")
    if reg_series:
        value = series_value_on_or_before(reg_series, today_ts)
        if value is not None and value >= regulatory_threshold:
            votes += 1

    etf_series = ctx.series.get("BTC_ETF_FLOW")
    if etf_series:
        value = series_value_on_or_before(etf_series, today_ts)
        if value is not None and value >= etf_threshold:
            votes += 1

    if votes >= min_votes:
        return "buy"
    return "hold"


LABEL = "Makro glasovanje (trend + Fed + Reddit + regulativa + ETF tokovi)"
DEFAULT_PARAMS = {
    "ema_trend": 200,
    "min_risk_on_votes": 3,
    "fed_lookback": 3,
    "reddit_threshold": 0.0,
    "regulatory_threshold": 0.0,
    "etf_threshold": 0.0,
}
