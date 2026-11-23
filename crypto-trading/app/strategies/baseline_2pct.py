"""Točna replika pravila iz priloženog istraživačkog paketa (kripto.py / PROCITAJ_ME.md), radi
usporedbe i radi provjere da backtest engine daje isti rezultat kao priloženi izvještaj
(508 -> 108,41 EUR, 2024-01-01 - 2026-11-21, BTC/EUR). Ovo pravilo prema vlastitom izvještaju
GUBI novac - zadržava se isključivo kao referentna točka, ne kao preporuka.
"""
from app.candles import Candle
from app.costs import FEE, SLIPPAGE


def run_baseline(candles: list[Candle], starting_balance: float, start_ts: int, end_ts: int) -> dict:
    by_time = {c.opened_at: c for c in candles}
    day = 86400
    capital = peak = starting_balance
    max_drawdown = 0.0
    closed_days = traded_days = winning_days = 0
    equity_curve = []

    for settled_at in range(start_ts + day, end_ts + 1, day):
        entry_ts = settled_at - day
        needed = [entry_ts - 3 * day, entry_ts - 2 * day, entry_ts, settled_at]
        if any(t not in by_time for t in needed):
            continue
        previous, latest, entry, exit_ = (by_time[t] for t in needed)
        signal = latest.close / previous.close - 1
        before = capital
        trade = signal >= 0.02
        if trade:
            buy = entry.open * (1 + SLIPPAGE)
            sell = exit_.open * (1 - SLIPPAGE)
            capital *= (sell / buy) * (1 - FEE) / (1 + FEE)
        closed_days += 1
        traded_days += trade
        winning_days += capital > before
        peak = max(capital, peak)
        max_drawdown = max(max_drawdown, 1 - capital / peak)
        equity_curve.append({"at": settled_at, "equity": round(capital, 4)})

    return {
        "strategy": "baseline_2pct",
        "trades": traded_days,
        "winning_trades": winning_days,
        "closed_days": closed_days,
        "starting_balance": starting_balance,
        "final_balance": round(capital, 2),
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "equity_curve": equity_curve,
    }
