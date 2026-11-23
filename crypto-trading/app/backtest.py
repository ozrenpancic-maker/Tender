"""Generički dnevni backtest engine: odluka se donosi nakon zatvaranja svijeće i, nakon
jednog dana zakašnjenja. To je ista konvencija vremena izvršenja kao u priloženom baznom testu."""
from app.candles import Candle, load_candles
from app.costs import COST_SCENARIOS, buy_fill_price, sell_fill_price, FEE, SLIPPAGE
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
    start_ts: int | None = None,
    fee: float = FEE,
    slippage: float = SLIPPAGE,
) -> dict:
    """`candles` može sadržavati dodatne "zagrijavajuće" svijeće PRIJE `start_ts` (da indikatori s
    dugim lookbackom, npr. SMA200, imaju povijest od prvog dana traženog razdoblja, ne tek nakon
    toliko dana unutar njega). `decide()` se poziva za SVAKI indeks (indikatori se ispravno
    zagrijavaju), ali se trgovine stvarno izvršavaju i equity_curve/trades broje samo od `start_ts`
    nadalje - portfelj kreće ravno (bez pozicije) na `start_ts`, isto kao u priloženom ChatGPT-ovom
    paralelnom istraživanju (`backtest_51.py`), radi usporedivosti i da zagrijavanje ne "izmisli"
    trgovine koje korisnik nije tražio."""
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
        next_candle = candles[i + 1]
        recording = start_ts is None or next_candle.opened_at >= start_ts

        ctx = StrategyContext(
            candles=candles, index=i, in_position=in_position if recording else False, params=params, aux=aux, series=series
        )
        decision = decide(ctx)
        if not recording:
            continue  # zagrijavanje: indikatori se pune, ali se ništa stvarno ne trguje/broji

        if decision == "buy" and not in_position:
            fill = buy_fill_price(next_candle.open, slippage)
            position_base = (cash * (1 - fee)) / fill
            entry_cash = cash
            cash = 0.0
            in_position = True
        elif decision == "sell" and in_position:
            fill = sell_fill_price(next_candle.open, slippage)
            cash = position_base * fill * (1 - fee)
            position_base = 0.0
            in_position = False
            trades += 1
            if cash > entry_cash:
                winning_trades += 1

        # Equity = STVARNA gotovina da bi se pozicija likvidirala SADA (sell_fill_price + FEE), ne
        # sirova mark-to-market cijena - nađeno u ChatGPT-ovoj neovisnoj reviziji: bez ovoga
        # usporedba "koliko stvarno imam" blago precjenjuje vrijednost dok je pozicija otvorena,
        # posebno na kraju testa ako se nikad ne prodalo. Ista konvencija kao ChatGPT-ov sim_hold.
        liquidated_value = position_base * sell_fill_price(next_candle.close, slippage) * (1 - fee) if position_base else 0.0
        equity = cash + liquidated_value
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


def run_buy_hold(candles: list[Candle], starting_balance: float, fee: float = FEE, slippage: float = SLIPPAGE) -> dict:
    """Referentna točka: kupi na prvoj svijeći, drži do kraja. Svaka aktivna strategija treba
    nadmašiti ovo da bi imala smisla (uz dodatni rizik aktivnog trgovanja).

    Trošak kupnje/prodaje mora biti IDENTIČNA formula kao u `run_generic_backtest` (nađeno u
    ChatGPT-ovoj neovisnoj reviziji dok je provjeravao zašto se buy_hold brojevi ne poklapaju do
    centa: ova funkcija je prije množila `buy_fill_price(open) * (1+FEE)` - approksimacija bliska
    `(1-FEE)` ali NE identična, davala je sustavno malo drugačiji rezultat od ostatka backtesta).
    Equity curve = stvarna gotovina da bi se likvidiralo SADA (sell_fill_price + FEE) na svakoj
    točki, ne sirova mark-to-market cijena - ista konvencija kao ChatGPT-ov sim_hold."""
    position_base = (starting_balance * (1 - fee)) / buy_fill_price(candles[0].open, slippage)
    equity_curve = [
        {"at": c.opened_at, "equity": round(position_base * sell_fill_price(c.close, slippage) * (1 - fee), 4)} for c in candles
    ]
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
    fee: float = FEE,
    slippage: float = SLIPPAGE,
) -> dict:
    if strategy_key == "buy_hold":
        candles = load_candles(conn, "binance", pair, interval_min, start_ts, end_ts)
        if len(candles) < 2:
            raise ValueError(f"Nema dovoljno svijeća za {pair} u traženom razdoblju.")
        return run_buy_hold(candles, starting_balance, fee, slippage)

    if strategy_key == "baseline_2pct":
        # Namjerno NEMA fee/slippage override - ovo reproducira TOČAN rezultat priloženog
        # izvještaja (vidi "Kako je provjereno"), promjena troškovnog modela bi to pokvarila.
        if pair != "BTC/EUR":
            raise ValueError("Bazno pravilo iz izvještaja definirano je samo za BTC/EUR.")
        day = 86400
        candles = load_candles(conn, "binance", pair, 1440, start_ts - 3 * day, end_ts)
        if len(candles) < 5:
            raise ValueError(f"Nema dovoljno dnevnih svijeća za {pair} u traženom razdoblju.")
        return run_baseline(candles, starting_balance, start_ts, end_ts)

    if strategy_key not in GENERIC_STRATEGIES:
        raise ValueError(f"Nepoznata strategija: {strategy_key}")

    # Zagrijavanje: učitaj dodatnu povijest PRIJE start_ts da indikatori s dugim lookbackom
    # (npr. SMA100/SMA200) imaju podatke od prvog dana traženog razdoblja - vidi run_generic_backtest.
    warmup_seconds = interval_min * 60 * 260
    candles = load_candles(conn, "binance", pair, interval_min, start_ts - warmup_seconds, end_ts)
    if len([c for c in candles if c.opened_at >= start_ts]) < 5:
        raise ValueError(f"Nema dovoljno svijeća za {pair} u traženom razdoblju (interval {interval_min} min).")

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

    return run_generic_backtest(candles, strategy_key, params, starting_balance, aux, series, start_ts, fee, slippage)


def run_cost_sensitivity(
    conn,
    strategy_key: str,
    pair: str,
    start_ts: int,
    end_ts: int,
    params: dict,
    starting_balance: float,
    interval_min: int = 1440,
) -> dict:
    """Pokreće ISTI backtest preko svih COST_SCENARIOS (vidi app/costs.py) - test osjetljivosti na
    pretpostavku o naknadama/slippageu, nađeno kao nedostatak u ChatGPT-ovoj neovisnoj reviziji
    ("realne naknade kao scenarij, ne fiksna pretpostavka"). Vraća {scenario_key: rezultat}."""
    results = {}
    for key, scenario in COST_SCENARIOS.items():
        try:
            r = run_backtest(
                conn, strategy_key, pair, start_ts, end_ts, params, starting_balance, interval_min,
                fee=scenario["fee"], slippage=scenario["slippage"],
            )
            results[key] = {"label": scenario["label"], "fee": scenario["fee"], "slippage": scenario["slippage"], **r}
        except ValueError as err:
            results[key] = {"label": scenario["label"], "error": str(err)}
    return results
