"""Stepenice: u širem uzlaznom trendu (zatvaranje iznad duge SMA), kupuje kad cijena kratkoročno
padne do/ispod donje Bollingerove vrpce (lokalno povlačenje), a prodaje čim se dogodi BILO KOJE od:
- dosegnut profit cilj (take_profit_pct) - "uhvaćena stepenica" prije sljedećeg pada
- cijena dosegne gornju vrpcu (lokalni vrh, isti mehanizam kao ulaz, samo obrnuto)
- probijen stop-loss (ograničava gubitak ako povlačenje nastavi padati umjesto odskoka)
- širi trend se slomi (zatvaranje padne ispod duge SMA - ne drži kroz pravi preokret)

Namijenjeno za kraće svijeće (1h) gdje se ovakve oscilacije stvarno vide više puta dnevno - na
dnevnim svijećama ovaj uzorak je prerijedak da bi bio koristan. Long-only (bez shortanja), isto
ograničenje kao sve ostale strategije u ovom projektu.

POŠTENO UPOZORENJE (vidi README "Stepenice - pošten nalaz" za potpuni nalaz): grid pretraga 72
kombinacija parametara na BTC/USDT satnim svijećama (in-sample 2023-11 do 2025-11, out-of-sample
2025-11 do 2026-11) pokazuje jasan kompromis - parametri dovoljno osjetljivi da trguju "više puta
dnevno" kako je zamišljeno (uski bb_std=1.5) GUBE katastrofalno (~94% pada, uhvate prave preokrete,
ne bezazlena povlačenja). Parametri ispod su NAJBOLJI pronađeni (bb_std=2.5, širi/rjeđi signal) i
dalje gube blago na OBA razdoblja (~8-12%, 5-16 trgovina u ~2 godine - rijetko, ne "više puta
dnevno"). Zaključak: ovaj točan pristup (BB donja/gornja vrpca + SMA trend filter) NEMA dokazanu
prednost nakon naknada/slippagea na dosad testiranim podacima - uključen je kao alat za dalje
istraživanje (probaj druge parove/indikatore), ne kao gotova preporuka."""
from app.indicators import bollinger_bands, sma
from app.strategies.base import Decision, StrategyContext


def decide(ctx: StrategyContext) -> Decision:
    trend_period = int(ctx.params.get("trend_period", 100))
    bb_period = int(ctx.params.get("bb_period", 20))
    bb_std = float(ctx.params.get("bb_std", 2.0))
    take_profit_pct = float(ctx.params.get("take_profit_pct", 0.02))
    stop_loss_pct = float(ctx.params.get("stop_loss_pct", 0.03))

    closes = [c.close for c in ctx.candles[: ctx.index + 1]]
    needed = max(trend_period, bb_period)
    if len(closes) < needed:
        return "hold"

    trend_ma = sma(closes, trend_period)
    bands = bollinger_bands(closes, bb_period, bb_std)
    if trend_ma is None or bands is None:
        return "hold"
    lower, _mid, upper = bands
    price = closes[-1]
    uptrend = price > trend_ma

    if ctx.in_position:
        entry_price = ctx.params.get("_entry_price")
        if entry_price:
            gain = price / entry_price - 1
            if gain >= take_profit_pct or gain <= -stop_loss_pct or price >= upper or not uptrend:
                ctx.params["_entry_price"] = None
                return "sell"
        return "hold"

    if uptrend and price <= lower:
        ctx.params["_entry_price"] = price
        return "buy"
    return "hold"


LABEL = "Stepenice (kupi povlačenje u trendu, prodaj na odskoku)"
DEFAULT_PARAMS = {
    "trend_period": 50,
    "bb_period": 20,
    "bb_std": 2.5,
    "take_profit_pct": 0.02,
    "stop_loss_pct": 0.03,
}
