"""Generički dnevni backtest engine: odluka se donosi nakon zatvaranja svijeće i, nakon
jednog dana zakašnjenja. To je ista konvencija vremena izvršenja kao u priloženom baznom testu."""
from app.candles import Candle, load_candles
from app.costs import COST_SCENARIOS, buy_fill_price, sell_fill_price, FEE, SLIPPAGE
from app.indicators import atr as _atr
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
    stop_loss_pct: float | None = None,
    risk_pct: float | None = None,
    atr_stop_mult: float | None = None,
    atr_period: int = 14,
    take_profit_r_multiple: float | None = None,
    max_consecutive_losses: int | None = None,
    max_daily_drawdown_pct: float | None = None,
) -> dict:
    """`candles` može sadržavati dodatne "zagrijavajuće" svijeće PRIJE `start_ts` (da indikatori s
    dugim lookbackom, npr. SMA200, imaju povijest od prvog dana traženog razdoblja, ne tek nakon
    toliko dana unutar njega). `decide()` se poziva za SVAKI indeks (indikatori se ispravno
    zagrijavaju), ali se trgovine stvarno izvršavaju i equity_curve/trades broje samo od `start_ts`
    nadalje - portfelj kreće ravno (bez pozicije) na `start_ts`, isto kao u priloženom ChatGPT-ovom
    paralelnom istraživanju (`backtest_51.py`), radi usporedivosti i da zagrijavanje ne "izmisli"
    trgovine koje korisnik nije tražio.

    `stop_loss_pct`/`risk_pct` (OBOJE opcionalni, zadano None = STAROM ponašanju, ništa se ne
    mijenja za postojeće pozive): dodano nakon što je korisnik pitao da provjerimo opću "pametnu"
    tvrdnju da je upravljanje rizikom (stop-loss + veličina pozicije prema riziku) važnije od
    "magičnog indikatora" - svih 16 strategija dosad nije imalo NIKAKAV stop-loss, čist izlaz samo
    na signal strategije. Ovo to popravlja kao TESTABILNU opciju, ne pretpostavku:
    - `stop_loss_pct` sam (bez risk_pct): postojeće "sve ili ništa" ulaganje, ali s tvrdim izlazom
      ako next_candle.low padne na/ispod entry*(1-stop_loss_pct) - provjerava se SVAKU svijeću dok
      je pozicija otvorena (ne samo na danima kad decide() nešto odluči), isto kao pravi stop-loss
      nalog na burzi koji je uvijek aktivan.
    - `risk_pct` UZ `stop_loss_pct` (ili `atr_stop_mult`): veličina pozicije tako da MAKSIMALNI
      gubitak po trgovini (ako stop-loss okine) bude otprilike `risk_pct` ukupnog kapitala, bez
      obzira na širinu stopa. Ostatak gotovine ostaje neuložen (idle) do sljedeće prilike.

    Dodano nakon konkretnog "bot pravilnika" koji je korisnik podijelio (ATR stop, R:R take-profit,
    zaštita računa) - SVE opcionalno, zadano None = ništa se ne mijenja za postojeće pozive:
    - `atr_stop_mult`/`atr_period`: stop = entry - ATR(`atr_period`)*`atr_stop_mult`, računat JEDNOM
      na ulasku (bounded prozor svijeća prije ulaska, ne cijela rastuća povijest - izbjegava isti
      O(n²) usporavanje nađen ranije kod stair_step_stochrsi). Ignorira se ako je `stop_loss_pct`
      također postavljen (taj ima prednost).
    - `take_profit_r_multiple`: izlaz kad next_candle.high dosegne entry + (entry-stop)*multiple -
      treba definiran stop (jedan od gornja dva), inače se ignorira (nema R-jedinice bez stopa).
    - `max_consecutive_losses`/`max_daily_drawdown_pct`: nakon N uzastopnih gubitaka ILI pada preko
      praga unutar istog kalendarskog dana (UTC), PAUZIRA nove ulaske do sljedećeg dana - postojeće
      otvorene pozicije i dalje poštuju stop/TP (zaštita se ne gasi), samo se ne otvaraju nove.

    Rezultat sad uključuje i `profit_factor` (ukupna dobit / ukupni gubitak, None ako nema gubitaka)
    i `avg_r_multiple` (prosjek po trgovini, samo za trgovine gdje je stop bio definiran na ulasku) -
    standardne mjere iz savjeta koji je korisnik podijelio, za pošteno vrednovanje bilo koje
    strategije, ne samo ove nove."""
    strategy = GENERIC_STRATEGIES[strategy_key]
    decide = strategy["decide"]
    params = {**strategy["default_params"], **params}
    aux = aux or {}
    series = series or {}

    cash = starting_balance
    position_base = 0.0
    in_position = False
    entry_price = None
    entry_cash = starting_balance
    stop_price_active = None
    tp_price_active = None
    trades = 0
    winning_trades = 0
    stop_loss_exits = 0
    take_profit_exits = 0
    trade_pnls: list[float] = []
    trade_r_multiples: list[float] = []
    peak = starting_balance
    max_drawdown = 0.0
    equity_curve = []

    consecutive_losses = 0
    trading_paused = False
    current_day_key = None
    day_start_equity = starting_balance

    # Procijenjen trošak PUNOG KRUGA (kupnja+prodaja) - nađeno kao stvaran bug pri provjeri
    # konkretnog "bot pravilnika" (vidi README): bez ovoga, risk_pct veličina pozicije ignorira
    # naknadu/slippage pri računanju koliko uložiti. Kad je stop uzak (npr. ATR-bazirani stop na
    # kratkim vremenskim okvirima, često <1% cijene) - uzak ili usporediv s troškom punog kruga -
    # formula bi ulagala OGROMAN dio kapitala da "sačuva" traženi risk_pct, a naknada se naplaćuje
    # na CIJELI uloženi iznos bez obzira na širinu stopa - stvaran gubitak po pogođenom stopu
    # ispadne višestruko veći od namjeravanog. Uključivanje ovog troška u nazivnik to sprječava.
    round_trip_cost_pct = 2 * (fee + slippage)

    def _record_closed_trade(pnl: float) -> None:
        nonlocal winning_trades, consecutive_losses, trading_paused
        trade_pnls.append(pnl)
        if stop_price_active is not None and entry_price:
            stop_distance_pct = (entry_price - stop_price_active) / entry_price
            risk_dollars = entry_cash * (stop_distance_pct + round_trip_cost_pct)
            if risk_dollars > 0:
                trade_r_multiples.append(pnl / risk_dollars)
        if pnl > 0:
            winning_trades += 1
            consecutive_losses = 0
        else:
            consecutive_losses += 1
            if max_consecutive_losses and consecutive_losses >= max_consecutive_losses:
                trading_paused = True

    for i in range(len(candles) - 1):
        next_candle = candles[i + 1]
        recording = start_ts is None or next_candle.opened_at >= start_ts

        if recording:
            day_key = next_candle.opened_at // 86400
            if current_day_key is None or day_key != current_day_key:
                current_day_key = day_key
                day_start_equity = equity_curve[-1]["equity"] if equity_curve else starting_balance
                trading_paused = False

        exited = False
        if recording and in_position and (stop_price_active is not None or tp_price_active is not None):
            if stop_price_active is not None and next_candle.low <= stop_price_active:
                fill = sell_fill_price(stop_price_active, slippage)
                proceeds = position_base * fill * (1 - fee)
                cash += proceeds
                trades += 1
                stop_loss_exits += 1
                _record_closed_trade(proceeds - entry_cash)
                position_base = 0.0
                in_position = False
                entry_price = stop_price_active = tp_price_active = None
                exited = True
            elif tp_price_active is not None and next_candle.high >= tp_price_active:
                fill = sell_fill_price(tp_price_active, slippage)
                proceeds = position_base * fill * (1 - fee)
                cash += proceeds
                trades += 1
                take_profit_exits += 1
                _record_closed_trade(proceeds - entry_cash)
                position_base = 0.0
                in_position = False
                entry_price = stop_price_active = tp_price_active = None
                exited = True

        ctx = StrategyContext(
            candles=candles, index=i, in_position=in_position if recording else False, params=params, aux=aux, series=series
        )
        decision = decide(ctx)
        if not recording:
            continue  # zagrijavanje: indikatori se pune, ali se ništa stvarno ne trguje/broji

        if not exited:
            if decision == "buy" and not in_position and not trading_paused:
                fill = buy_fill_price(next_candle.open, slippage)

                stop_price = None
                if stop_loss_pct:
                    stop_price = fill * (1 - stop_loss_pct)
                elif atr_stop_mult:
                    recent = candles[max(0, i - atr_period - 5): i + 1]
                    a = _atr(recent, atr_period)
                    if a:
                        stop_price = fill - a * atr_stop_mult

                fraction = 1.0
                if risk_pct and stop_price is not None and stop_price < fill:
                    stop_distance_pct = (fill - stop_price) / fill
                    fraction = min(1.0, risk_pct / (stop_distance_pct + round_trip_cost_pct))

                invest_amount = cash * fraction
                position_base = (invest_amount * (1 - fee)) / fill
                entry_cash = invest_amount
                entry_price = fill
                stop_price_active = stop_price
                tp_price_active = (
                    fill + (fill - stop_price) * take_profit_r_multiple
                    if (take_profit_r_multiple and stop_price is not None and stop_price < fill)
                    else None
                )
                cash -= invest_amount
                in_position = True
            elif decision == "sell" and in_position:
                fill = sell_fill_price(next_candle.open, slippage)
                proceeds = position_base * fill * (1 - fee)
                cash += proceeds
                trades += 1
                _record_closed_trade(proceeds - entry_cash)
                position_base = 0.0
                in_position = False
                entry_price = stop_price_active = tp_price_active = None

        # Equity = STVARNA gotovina da bi se pozicija likvidirala SADA (sell_fill_price + FEE), ne
        # sirova mark-to-market cijena - nađeno u ChatGPT-ovoj neovisnoj reviziji: bez ovoga
        # usporedba "koliko stvarno imam" blago precjenjuje vrijednost dok je pozicija otvorena,
        # posebno na kraju testa ako se nikad ne prodalo. Ista konvencija kao ChatGPT-ov sim_hold.
        liquidated_value = position_base * sell_fill_price(next_candle.close, slippage) * (1 - fee) if position_base else 0.0
        equity = cash + liquidated_value
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, 1 - equity / peak if peak > 0 else 0)
        equity_curve.append({"at": next_candle.opened_at, "equity": round(equity, 4)})

        if recording and max_daily_drawdown_pct and day_start_equity > 0:
            if 1 - equity / day_start_equity >= max_daily_drawdown_pct:
                trading_paused = True

    final_equity = equity_curve[-1]["equity"] if equity_curve else starting_balance

    gross_profit = sum(p for p in trade_pnls if p > 0)
    gross_loss = -sum(p for p in trade_pnls if p < 0)
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None
    avg_r_multiple = (sum(trade_r_multiples) / len(trade_r_multiples)) if trade_r_multiples else None

    return {
        "strategy": strategy_key,
        "params": params,
        "trades": trades,
        "winning_trades": winning_trades,
        "stop_loss_exits": stop_loss_exits,
        "take_profit_exits": take_profit_exits,
        "profit_factor": round(profit_factor, 3) if profit_factor is not None else None,
        "avg_r_multiple": round(avg_r_multiple, 3) if avg_r_multiple is not None else None,
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
    stop_loss_pct: float | None = None,
    risk_pct: float | None = None,
    atr_stop_mult: float | None = None,
    atr_period: int = 14,
    take_profit_r_multiple: float | None = None,
    max_consecutive_losses: int | None = None,
    max_daily_drawdown_pct: float | None = None,
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

    return run_generic_backtest(
        candles, strategy_key, params, starting_balance, aux, series, start_ts, fee, slippage, stop_loss_pct, risk_pct,
        atr_stop_mult, atr_period, take_profit_r_multiple, max_consecutive_losses, max_daily_drawdown_pct,
    )


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
