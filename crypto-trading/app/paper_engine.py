"""Paper trading: ista logika strategija kao u backtestu, ali odluke se donose nad živim
podacima s Coinbasea i simuliraju se ispunjenja po trenutnoj javnoj cijeni (bez pravog novca)."""
import json
import threading
import time

from app import coinbase_client, db, equity_client
from app.costs import MAKER_FEE, TAKER_FEE, taker_buy_fill, taker_sell_fill
from app.macro_clients import MACRO_CLIENTS
from app.strategies import GENERIC_STRATEGIES
from app.strategies.base import StrategyContext

POLL_INTERVAL_SECONDS = 300  # provjera svakih 5 minuta; odluka se donosi samo kad se pojavi nova zatvorena svijeća
CANDLE_LOOKBACK_COUNT = 400  # margina za indikatore s dugim lookbackom (npr. SMA200, trend_period=100)
MAKER_WAIT_TICKS = 3  # koliko ticka (5 min svaki = do 15 min) čekamo da se maker nalog ispuni prije isteka
VALID_EXECUTION_MODES = {"taker", "maker_post_only"}
STALE_QUOTE_SECONDS = 1800  # 30 min bez nove trgovine na Coinbaseu - velikodušno da ne lažno uzbunjuje na manje likvidnim parovima

_active_runs: dict[int, threading.Event] = {}
_lock = threading.Lock()


def _replay_state(conn, run_id: int) -> tuple[float, float, bool]:
    """Vraća (cash_eur, position_base, in_position) rekonstruirano iz zabilježenih trgovina. Naknada
    se bira po run-ovom execution_mode (maker/taker su jedna postavka za cijeli run, ne po trgovini)."""
    run = conn.execute("SELECT starting_balance_eur, execution_mode FROM paper_run WHERE id=?", (run_id,)).fetchone()
    fee = MAKER_FEE if run["execution_mode"] == "maker_post_only" else TAKER_FEE
    cash = run["starting_balance_eur"]
    position = 0.0
    for trade in conn.execute("SELECT side, price FROM paper_trade WHERE run_id=? ORDER BY id", (run_id,)):
        if trade["side"] == "buy":
            position = (cash * (1 - fee)) / trade["price"]
            cash = 0.0
        else:
            cash = position * trade["price"] * (1 - fee)
            position = 0.0
    return cash, position, position > 0


def _handle_pending_order(conn, run, bid: float, ask: float, now: int) -> None:
    """Maker (post-only) nalog koji čeka ispunjenje - 'dodir cijene na svijeći sam po sebi ne
    potvrđuje izvršenje': nalog čeka da tržište stvarno dođe do njegove cijene, s rokom isteka,
    umjesto da se pretpostavi trenutno ispunjenje kao kod taker naloga."""
    run_id = run["id"]
    side = run["pending_side"]
    limit_price = run["pending_limit_price"]
    ticks = run["pending_ticks"]

    if side == "buy":
        filled = ask <= limit_price
    else:
        filled = bid >= limit_price

    if filled:
        cash, position, _ = _replay_state(conn, run_id)
        if side == "buy":
            new_position = (cash * (1 - MAKER_FEE)) / limit_price
            conn.execute(
                "INSERT INTO paper_trade (run_id, side, price, balance_after_eur, position_after_base, executed_at, note)"
                " VALUES (?, 'buy', ?, 0, ?, ?, 'maker nalog ispunjen')",
                (run_id, limit_price, new_position, now),
            )
        else:
            new_cash = position * limit_price * (1 - MAKER_FEE)
            conn.execute(
                "INSERT INTO paper_trade (run_id, side, price, balance_after_eur, position_after_base, executed_at, note)"
                " VALUES (?, 'sell', ?, ?, 0, ?, 'maker nalog ispunjen')",
                (run_id, limit_price, new_cash, now),
            )
        conn.execute(
            "UPDATE paper_run SET pending_side=NULL, pending_limit_price=NULL, pending_posted_at=NULL, pending_ticks=0 WHERE id=?",
            (run_id,),
        )
    elif ticks + 1 >= MAKER_WAIT_TICKS:
        print(f"[paper_engine] run {run_id}: maker {side} nalog istekao neispunjen (tržište nije došlo do {limit_price}).")
        conn.execute(
            "UPDATE paper_run SET pending_side=NULL, pending_limit_price=NULL, pending_posted_at=NULL, pending_ticks=0 WHERE id=?",
            (run_id,),
        )
    else:
        conn.execute("UPDATE paper_run SET pending_ticks=? WHERE id=?", (ticks + 1, run_id))
    conn.commit()


def _check_daily_loss_limit(conn, run, equity_now: float, bid: float, position: float, now: int) -> bool:
    """Dnevni limit gubitka kao ZASEBNO pravilo (ChatGPT savjet, točka 4) - prati equity (ne samo
    realizirane trgovine), i ako je probijen, prisilno zatvara otvorenu poziciju (unaprijed
    definiran uvjet izlaza), ne čeka da strategija sama odluči prodati. Vraća True ako je run
    (novo ili već) zaustavljen za ostatak dana - pozivatelj onda preskače ostatak ticka."""
    run_id = run["id"]
    today = time.strftime("%Y-%m-%d", time.gmtime(now))

    if run["day_start_date"] != today:
        conn.execute(
            "UPDATE paper_run SET day_start_equity=?, day_start_date=?, daily_halted=0 WHERE id=?",
            (equity_now, today, run_id),
        )
        conn.commit()
        return False  # novi dan - referentna točka je upravo postavljena, nema smisla odmah provjeravati

    limit_pct = run["daily_loss_limit_pct"]
    if limit_pct is None or run["daily_halted"]:
        return bool(run["daily_halted"])

    day_start_equity = run["day_start_equity"]
    if day_start_equity and equity_now <= day_start_equity * (1 - limit_pct):
        print(f"[paper_engine] run {run_id}: dnevni limit gubitka ({limit_pct * 100:.1f}%) probijen - zaustavljam nove ulaze do sutra.")
        if position > 0:
            fill = taker_sell_fill(bid)
            new_cash = position * fill * (1 - TAKER_FEE)
            conn.execute(
                "INSERT INTO paper_trade (run_id, side, price, balance_after_eur, position_after_base, executed_at, note)"
                " VALUES (?, 'sell', ?, ?, 0, ?, 'prisilan izlaz - dnevni limit gubitka')",
                (run_id, fill, new_cash, now),
            )
        conn.execute(
            "UPDATE paper_run SET daily_halted=1, pending_side=NULL, pending_limit_price=NULL, pending_posted_at=NULL, pending_ticks=0 WHERE id=?",
            (run_id,),
        )
        conn.commit()
        return True
    return False


def _tick(run_id: int) -> None:
    conn = db.get_connection()
    try:
        run = conn.execute("SELECT * FROM paper_run WHERE id=? AND mode='paper'", (run_id,)).fetchone()
        if not run or run["status"] != "running":
            return

        pair = run["pair"]
        strategy_key = run["strategy"]
        params = json.loads(run["params_json"])
        interval_min = run["interval_min"]
        granularity = interval_min * 60
        product_id = coinbase_client.to_product_id(pair)

        try:
            ticker = coinbase_client.get_public_ticker(product_id)
        except Exception as err:
            conn.execute(
                "INSERT INTO paper_equity_point (run_id, at, equity_eur, price) VALUES (?, ?, ?, ?)",
                (run_id, int(time.time()), -1, -1),
            )
            conn.commit()
            print(f"[paper_engine] run {run_id}: ne mogu dohvatiti cijenu ({err})")
            return
        live_price, bid, ask, quote_age = ticker["price"], ticker["bid"], ticker["ask"], ticker.get("age_seconds")

        cash, position, in_position = _replay_state(conn, run_id)
        equity_now = cash + position * live_price
        now = int(time.time())
        conn.execute(
            "INSERT OR REPLACE INTO paper_equity_point (run_id, at, equity_eur, price) VALUES (?, ?, ?, ?)",
            (run_id, now, round(equity_now, 4), live_price),
        )
        conn.commit()

        # Zastarjela kotacija (ChatGPT savjet, točka 4): Coinbase je uspješno odgovorio, ali 'time'
        # (zadnja trgovina) je jako stara - moguć zamrznut feed. Pauziraj SVE odluke ovaj tick
        # (uključujući pending nalog provjeru, jer bi i ta provjera koristila sumnjiv bid/ask) -
        # equity točka iznad je svejedno zabilježena radi kontinuiteta grafa.
        if quote_age is not None and quote_age > STALE_QUOTE_SECONDS:
            print(f"[paper_engine] run {run_id}: kotacija zastarjela ({quote_age:.0f}s bez trgovine) - preskačem odluke ovaj tick.")
            return

        if _check_daily_loss_limit(conn, run, equity_now, bid, position, now):
            return

        # Maker (post-only) nalog koji čeka ispunjenje provjerava se na SVAKI tick (ne samo kad
        # stigne nova svijeća) - nalog treba vidjeti pomak cijene što prije moguće. Dok nalog čeka,
        # ne pokreće se nova odluka strategije (izbjegava dupli nalog na istu stranu).
        if run["pending_side"]:
            _handle_pending_order(conn, run, bid, ask, now)
            return

        try:
            candles = coinbase_client.get_public_candles_paginated(
                product_id, granularity=granularity, lookback_seconds=granularity * CANDLE_LOOKBACK_COUNT
            )
        except Exception as err:
            print(f"[paper_engine] run {run_id}: ne mogu dohvatiti svijeće ({err})")
            return

        if len(candles) < 5:
            return

        latest = candles[-1]
        if run["last_evaluated_candle_at"] == latest.opened_at:
            return  # ova svijeća (na ovom intervalu) je već obrađena

        strategy = GENERIC_STRATEGIES[strategy_key]
        aux = {}
        for label in strategy.get("needs_aux", []):
            try:
                aux[label] = equity_client.fetch_recent_candles(label, days=200)
            except Exception as err:
                print(f"[paper_engine] run {run_id}: ne mogu dohvatiti {label} ({err}) - preskačem ovaj tick.")
                return

        series = {}
        for spec in strategy.get("needs_series", []):
            try:
                client = MACRO_CLIENTS[spec["source"]]
                series[spec["series_id"]] = client.fetch_recent(spec["series_id"], days=400)
            except Exception as err:
                print(f"[paper_engine] run {run_id}: ne mogu dohvatiti {spec['series_id']} ({err}) - preskačem ovaj tick.")
                return

        ctx = StrategyContext(candles=candles, index=len(candles) - 1, in_position=in_position, params=params, aux=aux, series=series)
        decision = strategy["decide"](ctx)
        execution_mode = run["execution_mode"]

        if decision == "buy" and not in_position:
            if execution_mode == "maker_post_only":
                # Posti nalog NA trenutnom bidu (ne prelazi spread) - ispunjenje nije zajamčeno,
                # vidi _handle_pending_order. Nema paper_trade retka dok se stvarno ne ispuni.
                conn.execute(
                    "UPDATE paper_run SET pending_side='buy', pending_limit_price=?, pending_posted_at=?, pending_ticks=0 WHERE id=?",
                    (bid, now, run_id),
                )
            else:
                fill = taker_buy_fill(ask)
                new_position = (cash * (1 - TAKER_FEE)) / fill
                conn.execute(
                    "INSERT INTO paper_trade (run_id, side, price, balance_after_eur, position_after_base, executed_at, note)"
                    " VALUES (?, 'buy', ?, 0, ?, ?, ?)",
                    (run_id, fill, new_position, now, f"taker, signal na svijeći {latest.opened_at}"),
                )
        elif decision == "sell" and in_position:
            if execution_mode == "maker_post_only":
                conn.execute(
                    "UPDATE paper_run SET pending_side='sell', pending_limit_price=?, pending_posted_at=?, pending_ticks=0 WHERE id=?",
                    (ask, now, run_id),
                )
            else:
                fill = taker_sell_fill(bid)
                new_cash = position * fill * (1 - TAKER_FEE)
                conn.execute(
                    "INSERT INTO paper_trade (run_id, side, price, balance_after_eur, position_after_base, executed_at, note)"
                    " VALUES (?, 'sell', ?, ?, 0, ?, ?)",
                    (run_id, fill, new_cash, now, f"taker, signal na svijeći {latest.opened_at}"),
                )

        conn.execute("UPDATE paper_run SET last_evaluated_candle_at=? WHERE id=?", (latest.opened_at, run_id))
        conn.commit()
    finally:
        conn.close()


def _loop(run_id: int, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            _tick(run_id)
        except Exception as err:  # paper trading ne smije srušiti server zbog privremene greške
            print(f"[paper_engine] run {run_id}: neočekivana greška: {err}")
        stop_event.wait(POLL_INTERVAL_SECONDS)


VALID_INTERVALS_MIN = {60, 1440}  # 1h ili 1d (Coinbase javni feed ne nudi 4h izravno)


def start_run(
    strategy_key: str, params: dict, pair: str, starting_balance: float, interval_min: int = 1440,
    execution_mode: str = "taker", daily_loss_limit_pct: float | None = None,
) -> int:
    if strategy_key not in GENERIC_STRATEGIES:
        raise ValueError(f"Strategija '{strategy_key}' nije podržana za paper trading.")
    if interval_min not in VALID_INTERVALS_MIN:
        raise ValueError(f"Nepodržan interval {interval_min} min. Dostupno: {sorted(VALID_INTERVALS_MIN)}")
    if execution_mode not in VALID_EXECUTION_MODES:
        raise ValueError(f"Nepodržan execution_mode '{execution_mode}'. Dostupno: {sorted(VALID_EXECUTION_MODES)}")
    if daily_loss_limit_pct is not None and not 0 < daily_loss_limit_pct < 1:
        raise ValueError("daily_loss_limit_pct mora biti između 0 i 1 (npr. 0.05 = 5%), ili izostavljen za isključeno.")

    conn = db.get_connection()
    try:
        full_params = {**GENERIC_STRATEGIES[strategy_key]["default_params"], **params}
        today = time.strftime("%Y-%m-%d", time.gmtime())
        cur = conn.execute(
            "INSERT INTO paper_run (strategy, params_json, pair, started_at, starting_balance_eur, status, mode,"
            " interval_min, execution_mode, daily_loss_limit_pct, day_start_equity, day_start_date)"
            " VALUES (?, ?, ?, ?, ?, 'running', 'paper', ?, ?, ?, ?, ?)",
            (
                strategy_key, json.dumps(full_params), pair, int(time.time()), starting_balance, interval_min,
                execution_mode, daily_loss_limit_pct, starting_balance, today,
            ),
        )
        conn.commit()
        run_id = cur.lastrowid
    finally:
        conn.close()

    stop_event = threading.Event()
    with _lock:
        _active_runs[run_id] = stop_event
    thread = threading.Thread(target=_loop, args=(run_id, stop_event), daemon=True)
    thread.start()
    return run_id


def stop_run(run_id: int) -> None:
    with _lock:
        stop_event = _active_runs.pop(run_id, None)
    if stop_event:
        stop_event.set()

    conn = db.get_connection()
    try:
        conn.execute("UPDATE paper_run SET status='stopped', stopped_at=? WHERE id=?", (int(time.time()), run_id))
        conn.commit()
    finally:
        conn.close()


def resume_running_on_startup() -> None:
    """Pozvati pri pokretanju servera - ako je server bio ugašen dok je paper run bio 'running',
    ponovno pokreni njegovu pozadinsku petlju (stanje se uvijek rekonstruira iz baze)."""
    conn = db.get_connection()
    try:
        rows = conn.execute("SELECT id FROM paper_run WHERE status='running' AND mode='paper'").fetchall()
    finally:
        conn.close()
    for row in rows:
        stop_event = threading.Event()
        with _lock:
            _active_runs[row["id"]] = stop_event
        threading.Thread(target=_loop, args=(row["id"], stop_event), daemon=True).start()
