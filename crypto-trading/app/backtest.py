"""Generički dnevni backtest engine: odluka se donosi nakon zatvaranja svijeće i, nakon
jednog dana zakašnjenja. To je ista konvencija vremena izvršenja kao u priloženom baznom testu."""
from app.candles import Candle, load_candles
from app.costs import buy_fill_price, sell_fill_price, FEE
from app.macro_store import load_series
from app.strategies import GENERIC_STRATEGIES
from app.strategies.base import StrategyContext
from app.strategies.baseline_2pct import run_baseline


def run_generic_backtest(
    candles: list[Candle],
    strategy_key: str,
    params: dict,
    starting_balance: float,
    aux: dict | None = None,
    series: dict | None = None,
) -> dict:
    strategy = GENERIC_STRATEGIES[strategy_key]
    decide = strategy["decide"]
    params = {**strategy["default_params"], **params}
    aux = aux or {}
    series = series or {}

    cash = starting_balance
    position_base = 0.0
    in_position = False
    entry_cash = starting_balance
    trades = 0
    winning_trades = 0
    peak = starting_balance
    max_drawdown = 0.0
    equity_curve = []

    for i in range(len(candles) - 1):
        ctx = StrategyContext(candles=candles, index=i, in_position=in_position, params=params, aux=aux, series=series)
        decision = decide(ctx)
        next_candle = candles[i + 1]

        if decision == "buy" and not in_position:
            fill = buy_fill_price(next_candle.open)
            position_base = (cash * (1 - FEE)) / fill
            entry_cash = cash
            cash = 0.0
            in_position = True
        elif decision == "sell" and in_position:
            fill = sell_fill_price(next_candle.open)
            cash = position_base * fill * (1 - FEE)
            position_base = 0.0
            in_position = False
            trades += 1
            if cash > entry_cash:
                winning_trades += 1

        equity = cash + position_base * next_candle.close
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, 1 - equity / peak if peak > 0 else 0)
        equity_curve.append({"at": next_candle.opened_at, "equity": round(equity, 4)})

    final_equity = equity_curve[-1]["equity"] if equity_curve else starting_balance

    return {
        "strategy": strategy_key,
        "params": params,
        "trades": trades,
        "winning_trades": winning_trades,
        "starting_balance": starting_balance,
        "final_balance": round(final_equity, 2),
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "equity_curve": equity_curve,
    }


def run_buy_hold(candles: list[Candle], starting_balance: float) -> dict:
    """Referentna točka: kupi na prvoj svijeći, drži do kraja. Svaka aktivna strategija treba
    nadmašiti ovo da bi imala smisla (uz dodatni rizik aktivnog trgovanja)."""
    fill = buy_fill_price(candles[0].open) * (1 + FEE)
    position_base = starting_balance / fill
    equity_curve = [{"at": c.opened_at, "equity": round(position_base * c.close, 4)} for c in candles]
    peak = starting_balance
    max_drawdown = 0.0
    for point in equity_curve:
        peak = max(peak, point["equity"])
        max_drawdown = max(max_drawdown, 1 - point["equity"] / peak)
    return {
        "strategy": "buy_hold",
        "trades": 1,
        "winning_trades": 1 if equity_curve[-1]["equity"] > starting_balance else 0,
        "starting_balance": starting_balance,
        "final_balance": round(equity_curve[-1]["equity"], 2),
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "equity_curve": equity_curve,
    }


def run_backtest(
    conn,
    strategy_key: str,
    pair: str,
    start_ts: int,
    end_ts: int,
    params: dict,
    starting_balance: float,
    interval_min: int = 1440,
) -> dict:
    if strategy_key == "buy_hold":
        candles = load_candles(conn, "binance", pair, interval_min, start_ts, end_ts)
        if len(candles) < 2:
            raise ValueError(f"Nema dovoljno svijeća za {pair} u traženom razdoblju.")
        return run_buy_hold(candles, starting_balance)

    if strategy_key == "baseline_2pct":
        if pair != "BTC/EUR":
            raise ValueError("Bazno pravilo iz izvještaja definirano je samo za BTC/EUR.")
        day = 86400
        candles = load_candles(conn, "binance", pair, 1440, start_ts - 3 * day, end_ts)
        if len(candles) < 5:
            raise ValueError(f"Nema dovoljno dnevnih svijeća za {pair} u traženom razdoblju.")
        return run_baseline(candles, starting_balance, start_ts, end_ts)

    candles = load_candles(conn, "binance", pair, interval_min, start_ts, end_ts)
    if len(candles) < 5:
        raise ValueError(f"Nema dovoljno svijeća za {pair} u traženom razdoblju (interval {interval_min} min).")

    if strategy_key not in GENERIC_STRATEGIES:
        raise ValueError(f"Nepoznata strategija: {strategy_key}")

    aux = {}
    for label in GENERIC_STRATEGIES[strategy_key].get("needs_aux", []):
        aux_candles = load_candles(conn, "stooq", label, 1440, start_ts - 90 * 86400, end_ts)
        if not aux_candles:
            raise ValueError(
                f"Strategija '{strategy_key}' treba podatke za {label}, a nisu sinkronizirani. "
                f"Pokreni sync na dashboardu (odjeljak Wall Street) prvo."
            )
        aux[label] = aux_candles

    series = {}
    for spec in GENERIC_STRATEGIES[strategy_key].get("needs_series", []):
        points = load_series(conn, spec["source"], spec["series_id"], start_ts - 365 * 86400, end_ts)
        if not points:
            raise ValueError(
                f"Strategija '{strategy_key}' treba podatke '{spec['series_id']}' ({spec['source']}), "
                f"a nisu sinkronizirani. Pokreni sync na dashboardu (odjeljak Makro/sentiment) prvo."
            )
        series[spec["series_id"]] = points

    return run_generic_backtest(candles, strategy_key, params, starting_balance, aux, series)
