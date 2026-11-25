"""Stepenice v2: isti cilj kao stair_step_swing (kupi povlačenje u trendu, prodaj na odskoku), ali
drugi mehanizam - umjesto dodira Bollingerove vrpce, koristi Stochastic RSI PRESJEK (ne razinu):
kupuje kad %K presječe PREKO granice prenisprodanosti (izlazak iz prenisprodanosti = počinje
odskok), u širem uzlaznom trendu (SMA filter). Prodaje na simetričan presjek PREKO granice
prekupljenosti, na stop-loss, ili na slom trenda.

Zašto presjek, ne razina: čista razina (%K < 20) ostaje true cijelo vrijeme dok je indikator nisko
- presjek (prelazak s donje na gornju stranu granice) hvata TRENUTAK zaokreta, ne cijelo razdoblje
niske vrijednosti, pa bi trebao manje preklapati s dubokim padom koji TEK počinje.

Long-only (bez shortanja), isti troškovni model kao sve ostale strategije u ovom projektu.

POŠTEN REZULTAT (vidi README "Stepenice v2" za potpun nalaz): ovo je GORE od prve verzije
(Bollingerove vrpce) - presjek preko granice prenisprodanosti/prekupljenosti okida se prečesto
(130-290 trgovina kroz 9-24 mjeseca, otprilike svaka 2-5 dana), a naknade (~1% round-trip) na toliko
trgovina jedu gotovo sav kapital. Grid pretraga 81 kombinacije na BTC/USDT satnim svijećama - NAJBOLJA
pronađena kombinacija izgubila je ~94% in-sample i ~90% out-of-sample. Nijedna testirana kombinacija
nije bila blizu profitabilnosti. NE koristi ovu strategiju - uključena je isključivo kao
dokumentirani negativan nalaz (druga strategija koja ovo isprobava drugim mehanizmom)."""
from app.indicators import sma, stochastic_rsi
from app.strategies.base import Decision, StrategyContext


def decide(ctx: StrategyContext) -> Decision:
    trend_period = int(ctx.params.get("trend_period", 50))
    rsi_period = int(ctx.params.get("rsi_period", 14))
    stoch_period = int(ctx.params.get("stoch_period", 14))
    oversold = float(ctx.params.get("oversold", 20.0))
    overbought = float(ctx.params.get("overbought", 80.0))
    stop_loss_pct = float(ctx.params.get("stop_loss_pct", 0.03))

    closes = [c.close for c in ctx.candles[: ctx.index + 1]]
    needed = max(trend_period, rsi_period + stoch_period + 1)
    if len(closes) < needed:
        return "hold"

    trend_ma = sma(closes, trend_period)
    # stochastic_rsi() interno računa rsi_series() preko CIJELOG niza koji mu se da - ako bismo
    # proslijedili rastući `closes` (sva povijest do sad), svaki poziv bi bio O(n), a decide() se
    # zove O(n) puta kroz backtest => O(n^2)/O(n^3) ukupno (stvarno izmjereno: >30 min, nije
    # završilo). Rješenje: proslijedi samo zadnjih `window` cijena - stochastic_rsi treba samo toliko
    # povijesti da izračuna stabilan %K, rezultat je identičan jer rsi()/stochastic_rsi gledaju samo
    # unatrag kroz fiksan broj perioda, nikad dalje.
    window = rsi_period + stoch_period + 5
    k_now = stochastic_rsi(closes[-window:], rsi_period, stoch_period)
    k_prev = stochastic_rsi(closes[-window - 1 : -1], rsi_period, stoch_period)
    if trend_ma is None or k_now is None or k_prev is None:
        return "hold"

    price = closes[-1]
    uptrend = price > trend_ma

    if ctx.in_position:
        entry_price = ctx.params.get("_entry_price")
        crossed_down_overbought = k_prev >= overbought and k_now < overbought
        if entry_price:
            gain = price / entry_price - 1
            if crossed_down_overbought or gain <= -stop_loss_pct or not uptrend:
                ctx.params["_entry_price"] = None
                return "sell"
        return "hold"

    crossed_up_oversold = k_prev <= oversold and k_now > oversold
    if uptrend and crossed_up_oversold:
        ctx.params["_entry_price"] = price
        return "buy"
    return "hold"


LABEL = "Stepenice v2 (Stochastic RSI presjek + trend filter)"
DEFAULT_PARAMS = {
    "trend_period": 50,
    "rsi_period": 14,
    "stoch_period": 14,
    "oversold": 20.0,
    "overbought": 80.0,
    "stop_loss_pct": 0.03,
}
