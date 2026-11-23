"""Trend Guard: SMA presjek (brzi/spori) uz dodatni regime-filter - kupuje samo kad je cijena i
iznad srednjeg (100-dnevnog) prosjeka, prodaje čim jedan od ta dva uvjeta otpadne.

Podrijetlo: port ChatGPT-ovog "guard_10_40" iz paralelnog istraživanja (KriptoMVP 5.1 paket,
`backtest_51.py`), gdje je bio najbolji samo na razvojnim godinama (2021-2024), a na 2025-26 dao
117,04 € od 100 € (manji profit, ali i manji pad od čistog SMA10/40) - ne dokazana prednost, vidi
README. Logika ovdje je preformulirana za ovaj projekt (per-bar `decide()`, ne vektorizirani
pandas), ali ekvivalentna: "ostani uložen dok traje potvrđen trend, izađi čim bilo koji uvjet
otpadne" - funkcionalno isto kao presjek koji zahtijeva i smjer i poziciju iznad regime-filtera."""
from app.strategies.base import Decision, StrategyContext


def _sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def decide(ctx: StrategyContext) -> Decision:
    fast_n = int(ctx.params.get("fast", 10))
    slow_n = int(ctx.params.get("slow", 40))
    trend_n = int(ctx.params.get("trend_period", 100))
    closes = [c.close for c in ctx.candles[: ctx.index + 1]]

    needed = max(slow_n, trend_n)
    if len(closes) < needed:
        return "hold"

    fast_ma, slow_ma, trend_ma = _sma(closes, fast_n), _sma(closes, slow_n), _sma(closes, trend_n)
    if None in (fast_ma, slow_ma, trend_ma):
        return "hold"

    guard_ok = fast_ma > slow_ma and closes[-1] > trend_ma

    if guard_ok and not ctx.in_position:
        return "buy"
    if not guard_ok and ctx.in_position:
        return "sell"
    return "hold"


LABEL = "Trend Guard (SMA presjek + 100-dnevni regime filter)"
DEFAULT_PARAMS = {"fast": 10, "slow": 40, "trend_period": 100}
