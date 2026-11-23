"""Paper trading: ista logika strategija kao u backtestu, ali odluke se donose nad živim
podacima s Coinbasea i simuliraju se ispunjenja po trenutnoj javnoj cijeni (bez pravog novca)."""
import json
import threading
import time

from app import coinbase_client, db
from app.costs import FEE, buy_fill_price, sell_fill_price
from app.strategies import GENERIC_STRATEGIES
from app.strategies.base import StrategyContext

POLL_INTERVAL_SECONDS = 300  # provjera svakih 5 minuta; odluka se donosi samo kad se pojavi nova zatvorena dnevna svijeća

_active_runs: dict[int, threading.Event] = {}
_lock = threading.Lock()


def _replay_state(conn, run_id: int) -> tuple[float, float, bool]:
    """Vraća (cash_eur, position_base, in_position) rekonstruirano iz zabilježenih trgovina."""
    run = conn.execute("SELECT starting_balance_eur FROM paper_run WHERE id=?", (run_id,)).fetchone()
    cash = run["starting_balance_eur"]
    position = 0.0
    for trade in conn.execute("SELECT side, price FROM paper_trade WHERE run_id=? ORDER BY id", (run_id,)):
        if trade["side"] == "buy":
            position = (cash * (1 - FEE)) / trade["price"]
            cash = 0.0
        else:
            cash = position * trade["price"] * (1 - FEE)
            position = 0.0
    return cash, position, position > 0


def _tick(run_id: int) -> None:
    conn = db.get_connection()
    try:
        run = conn.execute("SELECT * FROM paper_run WHERE id=? AND mode='paper'", (run_id,)).fetchone()
        if not run or run["status"] != "running":
            return

        pair = run["pair"]
        strategy_key = run["strategy"]
        params = json.loads(run["params_json"])
        product_id = coinbase_client.to_product_id(pair)

        try:
            live_price = coinbase_client.get_public_price(product_id)
        except Exception as err:
            conn.execute(
                "INSERT INTO paper_equity_point (run_id, at, equity_eur, price) VALUES (?, ?, ?, ?)",
                (run_id, int(time.time()), -1, -1),
            )
            conn.commit()
            print(f"[paper_engine] run {run_id}: ne mogu dohvatiti cijenu ({err})")
            return

        cash, position, in_position = _replay_state(conn, run_id)
        equity_now = cash + position * live_price
        now = int(time.time())
        conn.execute(
            "INSERT OR REPLACE INTO paper_equity_point (run_id, at, equity_eur, price) VALUES (?, ?, ?, ?)",
            (run_id, now, round(equity_now, 4), live_price),
        )
        conn.commit()

        try:
            candles = coinbase_client.get_public_daily_candles(product_id, days=120)
        except Exception as err:
            print(f"[paper_engine] run {run_id}: ne mogu dohvatiti svijeće ({err})")
            return

        if len(candles) < 5:
            return

        latest = candles[-1]
        if run["last_evaluated_candle_at"] == latest.opened_at:
            return  # ova dnevna svijeća je već obrađena

        strategy = GENERIC_STRATEGIES[strategy_key]
        ctx = StrategyContext(candles=candles, index=len(candles) - 1, in_position=in_position, params=params)
        decision = strategy["decide"](ctx)

        if decision == "buy" and not in_position:
            fill = buy_fill_price(live_price)
            new_position = (cash * (1 - FEE)) / fill
            conn.execute(
                "INSERT INTO paper_trade (run_id, side, price, balance_after_eur, position_after_base, executed_at, note)"
                " VALUES (?, 'buy', ?, 0, ?, ?, ?)",
                (run_id, fill, new_position, now, f"signal na svijeći {latest.opened_at}"),
            )
        elif decision == "sell" and in_position:
            fill = sell_fill_price(live_price)
            new_cash = position * fill * (1 - FEE)
            conn.execute(
                "INSERT INTO paper_trade (run_id, side, price, balance_after_eur, position_after_base, executed_at, note)"
                " VALUES (?, 'sell', ?, ?, 0, ?, ?)",
                (run_id, fill, new_cash, now, f"signal na svijeći {latest.opened_at}"),
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


def start_run(strategy_key: str, params: dict, pair: str, starting_balance: float) -> int:
    if strategy_key not in GENERIC_STRATEGIES:
        raise ValueError(f"Strategija '{strategy_key}' nije podržana za paper trading.")

    conn = db.get_connection()
    try:
        full_params = {**GENERIC_STRATEGIES[strategy_key]["default_params"], **params}
        cur = conn.execute(
            "INSERT INTO paper_run (strategy, params_json, pair, started_at, starting_balance_eur, status, mode)"
            " VALUES (?, ?, ?, ?, ?, 'running', 'paper')",
            (strategy_key, json.dumps(full_params), pair, int(time.time()), starting_balance),
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
