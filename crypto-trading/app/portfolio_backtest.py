"""Portfelj trend strategija preko više coinova, s veličinom pozicije prema volatilnosti - najbliže
onome što profesionalni CTA / managed futures fondovi stvarno rade ("time-series momentum"), za
razliku od biranja JEDNE strategije na JEDNOM paru.

Kako radi (dnevno, odluka nakon zatvaranja svijeće, izvršenje na otvaranju sljedeće - ista
konvencija kao app/backtest.py):
1. Svaka strategija na svakom paru vodi svoje vlastito virtualno stanje (u poziciji / van), točno
   kao da radi sama - `decide()` dobiva isti StrategyContext kao u običnom backtestu.
2. Signal para = udio strategija koje su "u poziciji" (npr. 2 od 3 = 0.67). Slaganje strategija
   povećava izloženost, neslaganje je smanjuje - ansambl umjesto jednog glasa.
3. Rizični budžet se dijeli JEDNAKO po parovima prema inverznoj volatilnosti (zadnjih 30 dana):
   miran coin dobiva veću poziciju, divlji (npr. SOL) manju, tako da svaki nosi sličan rizik.
4. Opcionalno ciljanje volatilnosti portfelja (`target_vol`): kad je tržište divlje, cijeli
   portfelj se smanjuje. Procjena volatilnosti portfelja pretpostavlja POTPUNU korelaciju
   coinova (konzervativno - kripto je visoko koreliran, pogotovo u padovima).
5. Bez poluge: zbroj težina nikad > 1, ostatak je gotovina.
6. Rebalans samo kad se signal para promijeni ili težina odluta > `rebalance_drift` relativno
   (zadano 1.0 = težina se udvostručila/prepolovila). Testirano 0.25/0.5/1.0/samo-signal na
   2021-2025: broj trgovina se jedva mijenja (556 -> 516, promet dolazi od promjena SIGNALA, ne od
   dnevnog štimanja težina), Sharpe 0.94 -> 0.98 - mala razlika, izabrano manje intervencije
   iz principa (manje trgovanja = manje troškova), ne zato što je "pobijedilo".

`compute_target_weights` (odluke) je namjerno odvojen od `run_portfolio_backtest` (izvršenje), da
app/checks.py može provjeriti look-ahead bias na samom sloju odluka.
"""
import math

from app.candles import Candle, load_candles
from app.costs import FEE, SLIPPAGE, buy_fill_price, sell_fill_price
from app.strategies import GENERIC_STRATEGIES
from app.strategies.base import StrategyContext

DEFAULT_STRATEGIES = ["ema_trend", "trend_guard", "vol_guarded_trend"]
DEFAULT_PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"]
# Za usporedbu "zašto ne sve strategije odjednom" (vidi README) - sve trend strategije koje rade
# samo na cijeni. Ostale cjenovne (rsi_meanrev, dip_buy_volume, stair_step_*) su kontra/swing.
TREND_STRATEGIES = [
    "sma_crossover", "technical_composite", "trend_guard", "ema_trend",
    "confirmed_trend", "donchian_breakout", "dual_momentum", "vol_guarded_trend",
]


def price_only_strategies() -> list[str]:
    """Sve strategije kojima treba samo cijena (portfelj ne podržava makro/derivate podatke)."""
    return [k for k, v in GENERIC_STRATEGIES.items() if not v.get("needs_aux") and not v.get("needs_series")]
VOL_LOOKBACK_DAYS = 30
DAYS_PER_YEAR = 365  # kripto trguje i vikendom
WARMUP_DAYS = 260
MIN_TRADE_FRACTION = 0.01  # trgovine manje od 1% vrijednosti portfelja se preskaču (naknada > korist)


def _realized_vol(candles: list[Candle], index: int, lookback: int = VOL_LOOKBACK_DAYS) -> float | None:
    if index < lookback:
        return None
    closes = [c.close for c in candles[index - lookback: index + 1]]
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    vol = math.sqrt(var) * math.sqrt(DAYS_PER_YEAR)
    return vol if vol > 0 else None


def common_dates(candles_by_pair: dict[str, list[Candle]], start_ts: int) -> list[int]:
    sets = [{c.opened_at for c in cs if c.opened_at >= start_ts} for cs in candles_by_pair.values()]
    return sorted(set.intersection(*sets)) if sets else []


def compute_target_weights(
    candles_by_pair: dict[str, list[Candle]],
    strategies: list[str],
    start_ts: int,
    target_vol: float | None = None,
) -> list[tuple[int, dict[str, float], dict[str, float], dict[str, float]]]:
    """Vraća [(datum_odluke, {par: ciljna_težina}, {par: signal}, {par: volatilnost}), ...] - odluka
    na datumu t koristi SAMO svijeće zaključno s t. Volatilnost se vraća zasebno da app/checks.py
    može provjeriti look-ahead i kad su svi signali 0 (tada su sve težine 0 pa bi bug u procjeni
    volatilnosti bio nevidljiv). Virtualna stanja strategija kreću "van pozicije" na start_ts (isto
    kao run_generic_backtest - zagrijavanje puni indikatore, ali ne izmišlja trgovine)."""
    dates = common_dates(candles_by_pair, start_ts)
    index_of = {p: {c.opened_at: i for i, c in enumerate(cs)} for p, cs in candles_by_pair.items()}
    state = {(s, p): False for s in strategies for p in candles_by_pair}
    out = []

    for t in dates:
        signals: dict[str, float] = {}
        vols: dict[str, float] = {}
        for p, cs in candles_by_pair.items():
            idx = index_of[p][t]
            for s in strategies:
                strat = GENERIC_STRATEGIES[s]
                ctx = StrategyContext(
                    candles=cs, index=idx, in_position=state[(s, p)],
                    params=dict(strat["default_params"]), aux={}, series={},
                )
                d = strat["decide"](ctx)
                if d == "buy" and not state[(s, p)]:
                    state[(s, p)] = True
                elif d == "sell" and state[(s, p)]:
                    state[(s, p)] = False
            signals[p] = sum(state[(s, p)] for s in strategies) / len(strategies)
            v = _realized_vol(cs, idx)
            if v is not None:
                vols[p] = v

        weights = {p: 0.0 for p in candles_by_pair}
        if vols:
            inv_sum = sum(1 / v for v in vols.values())
            for p, v in vols.items():
                weights[p] = signals[p] * (1 / v) / inv_sum
            if target_vol:
                # Potpuna korelacija => vol portfelja ~ zbroj(težina * vol). Konzervativno.
                est_vol = sum(weights[p] * vols[p] for p in vols)
                if est_vol > target_vol:
                    scale = target_vol / est_vol
                    weights = {p: w * scale for p, w in weights.items()}
        out.append((t, weights, signals, vols))
    return out


def _metrics(equity_curve: list[dict], starting_balance: float) -> dict:
    eq = [p["equity"] for p in equity_curve]
    if len(eq) < 2:
        return {}
    rets = [eq[i] / eq[i - 1] - 1 for i in range(1, len(eq)) if eq[i - 1] > 0]
    mean = sum(rets) / len(rets)
    std = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)) if len(rets) > 1 else 0.0
    years = len(eq) / DAYS_PER_YEAR
    final = eq[-1]
    cagr = (final / starting_balance) ** (1 / years) - 1 if final > 0 and years > 0 else -1.0
    peak, max_dd = eq[0], 0.0
    for v in eq:
        peak = max(peak, v)
        max_dd = max(max_dd, 1 - v / peak if peak > 0 else 0)

    yearly: dict[str, float] = {}
    import time as _t
    by_year: dict[str, list[float]] = {}
    for p in equity_curve:
        by_year.setdefault(_t.strftime("%Y", _t.gmtime(p["at"])), []).append(p["equity"])
    prev_end = starting_balance
    for y in sorted(by_year):
        vals = by_year[y]
        yearly[y] = round((vals[-1] / prev_end - 1) * 100, 1)
        prev_end = vals[-1]

    return {
        "final_balance": round(final, 2),
        "total_return_pct": round((final / starting_balance - 1) * 100, 1),
        "cagr_pct": round(cagr * 100, 1),
        "annual_vol_pct": round(std * math.sqrt(DAYS_PER_YEAR) * 100, 1),
        "sharpe": round(mean / std * math.sqrt(DAYS_PER_YEAR), 2) if std > 0 else None,
        "max_drawdown_pct": round(max_dd * 100, 1),
        "calmar": round(cagr / max_dd, 2) if max_dd > 0 else None,
        "yearly_return_pct": yearly,
    }


def run_portfolio_backtest(
    candles_by_pair: dict[str, list[Candle]],
    strategies: list[str],
    starting_balance: float,
    start_ts: int,
    target_vol: float | None = None,
    rebalance_drift: float = 1.0,
    fee: float = FEE,
    slippage: float = SLIPPAGE,
    min_trade_fraction: float = MIN_TRADE_FRACTION,
) -> dict:
    decisions = compute_target_weights(candles_by_pair, strategies, start_ts, target_vol)
    if len(decisions) < 2:
        raise ValueError("Premalo zajedničkih dana za portfeljni backtest.")
    by_ts = {p: {c.opened_at: c for c in cs} for p, cs in candles_by_pair.items()}

    cash = starting_balance
    units = {p: 0.0 for p in candles_by_pair}
    last_signal = {p: 0.0 for p in candles_by_pair}
    equity_curve = []
    trades = 0
    fees_paid = 0.0
    turnover = 0.0
    exposure_sum = 0.0
    equity_sum = 0.0

    for k in range(len(decisions) - 1):
        _, targets, signals, _ = decisions[k]
        t_exec = decisions[k + 1][0]
        opens = {p: by_ts[p][t_exec].open for p in units}
        value = cash + sum(units[p] * opens[p] for p in units)

        orders: dict[str, float] = {}
        for p in units:
            cur_w = units[p] * opens[p] / value if value > 0 else 0.0
            tgt_w = targets[p]
            signal_changed = signals[p] != last_signal[p]
            drifted = abs(tgt_w - cur_w) > rebalance_drift * max(tgt_w, cur_w)
            if (signal_changed or drifted) and abs(tgt_w - cur_w) >= min_trade_fraction:
                orders[p] = (tgt_w - cur_w) * value
            elif tgt_w == 0 and units[p] > 0:
                orders[p] = -units[p] * opens[p]  # izađi potpuno kad signal padne na nulu
        last_signal = dict(signals)

        for p, delta in sorted(orders.items(), key=lambda kv: kv[1]):  # prodaje prve, oslobode gotovinu
            if delta < 0:
                sell_units = min(units[p], -delta / opens[p])
                proceeds = sell_units * sell_fill_price(opens[p], slippage) * (1 - fee)
                fees_paid += sell_units * opens[p] - proceeds
                turnover += sell_units * opens[p]
                units[p] -= sell_units
                cash += proceeds
                trades += 1
            else:
                spend = min(delta, cash)
                if spend <= 0:
                    continue
                bought = spend * (1 - fee) / buy_fill_price(opens[p], slippage)
                fees_paid += spend - bought * opens[p]
                turnover += spend
                units[p] += bought
                cash -= spend
                trades += 1

        closes = {p: by_ts[p][t_exec].close for p in units}
        liquidation = sum(units[p] * sell_fill_price(closes[p], slippage) * (1 - fee) for p in units if units[p] > 0)
        equity = cash + liquidation
        gross = sum(units[p] * closes[p] for p in units)
        exposure_sum += gross / (cash + gross) if (cash + gross) > 0 else 0
        equity_sum += equity
        equity_curve.append({"at": t_exec, "equity": round(equity, 4)})

    days = len(equity_curve)
    avg_equity = equity_sum / days if days else starting_balance
    return {
        "strategies": strategies,
        "pairs": list(candles_by_pair),
        "target_vol": target_vol,
        "rebalance_drift": rebalance_drift,
        "min_trade_fraction": min_trade_fraction,
        "starting_balance": starting_balance,
        "trades": trades,
        "fees_paid": round(fees_paid, 2),
        "fees_pct_of_avg_equity_per_year": round(100 * fees_paid / avg_equity / (days / DAYS_PER_YEAR), 2) if days else None,
        # Promet u odnosu na PROSJEČNU vrijednost portfelja (ne početnu - portfelj koji naraste 3x bi
        # inače izgledao kao da trguje 3x više nego stvarno).
        "annual_turnover_x": round(turnover / avg_equity / (days / DAYS_PER_YEAR), 2) if days else None,
        "avg_exposure_pct": round(100 * exposure_sum / days, 1) if days else None,
        **_metrics(equity_curve, starting_balance),
        "equity_curve": equity_curve,
    }


def run_equal_weight_buy_hold(
    candles_by_pair: dict[str, list[Candle]], starting_balance: float, start_ts: int,
    fee: float = FEE, slippage: float = SLIPPAGE,
) -> dict:
    dates = common_dates(candles_by_pair, start_ts)
    by_ts = {p: {c.opened_at: c for c in cs} for p, cs in candles_by_pair.items()}
    per = starting_balance / len(candles_by_pair)
    units = {p: per * (1 - fee) / buy_fill_price(by_ts[p][dates[0]].open, slippage) for p in candles_by_pair}
    curve = [
        {"at": t, "equity": round(sum(units[p] * sell_fill_price(by_ts[p][t].close, slippage) * (1 - fee) for p in units), 4)}
        for t in dates[1:]
    ]
    return {"strategy": "buy_hold_equal_weight", "starting_balance": starting_balance, **_metrics(curve, starting_balance), "equity_curve": curve}


def load_portfolio_candles(conn, pairs: list[str], start_ts: int, end_ts: int) -> dict[str, list[Candle]]:
    out = {}
    for p in pairs:
        cs = load_candles(conn, "binance", p, 1440, start_ts - WARMUP_DAYS * 86400, end_ts)
        if len([c for c in cs if c.opened_at >= start_ts]) < 30:
            raise ValueError(f"Nema dovoljno dnevnih svijeća za {p} u traženom razdoblju - sinkroniziraj povijest prvo.")
        out[p] = cs
    return out
