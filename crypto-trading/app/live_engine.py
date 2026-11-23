"""Live trading: ISTA logika kao paper_engine, ali umjesto simulacije šalje prave naloge na
Coinbase s pravim novcem.

SIGURNOSNA KOČNICA (više slojeva, namjerno):
1. config.LIVE_TRADING_ENABLED mora biti True (environment varijabla LIVE_TRADING_ENABLED=true) -
   provjerava se i pri pokretanju i pri svakom pojedinačnom slanju naloga.
2. config.LIVE_MAX_POSITION_EUR ograničava koliko EUR jedan 'buy' nalog smije potrošiti.
3. config.LIVE_DAILY_LOSS_LIMIT_EUR - ako dnevni gubitak premaši ovaj iznos, run se automatski
   zaustavlja i više ne šalje naloge dok ga se ručno ponovno ne pokrene.
Ništa od ovoga ne zamjenjuje tvoju vlastitu procjenu rizika - ovo je razvojni kod koji NIJE uživo
testiran protiv pravog Coinbase računa (vidi napomenu u coinbase_client.py).
"""
import json
import threading
import time

from app import coinbase_client, config, db, equity_client
from app.macro_clients import MACRO_CLIENTS
from app.strategies import GENERIC_STRATEGIES
from app.strategies.base import StrategyContext

POLL_INTERVAL_SECONDS = 300

_active_runs: dict[int, threading.Event] = {}
_lock = threading.Lock()


class LiveTradingDisabled(Exception):
    pass


def _check_enabled() -> None:
    if not config.LIVE_TRADING_ENABLED:
        raise LiveTradingDisabled(
            "LIVE_TRADING_ENABLED nije uključen u .env. Ovo je namjerno - uključi ga tek kad si "
            "svjestan/na rizika i prošao/la paper trading fazu."
        )


def _cash_flow_since(conn, run_id: int, since_ts: int) -> tuple[float, bool]:
    """Neto novčani tok (prodaje - kupnje) od since_ts za ovaj run. `ok=False` znači da
    odgovor Coinbasea za neki nalog nije imao polje koje očekujemo - u tom slučaju gubitak nije
    pouzdano izmjeren i tretiramo ga kao da je limit probijen (fail-safe)."""
    total = 0.0
    ok = True
    for order in conn.execute(
        "SELECT side, requested_eur, raw_response FROM live_order WHERE run_id=? AND status='filled' AND created_at>=?",
        (run_id, since_ts),
    ):
        raw = json.loads(order["raw_response"] or "{}")
        if order["side"] == "buy":
            if order["requested_eur"] is None:
                ok = False
                continue
            total -= order["requested_eur"]
        else:
            proceeds = raw.get("filled_value") or raw.get("total_value_after_fees")
            if proceeds is None:
                ok = False
                continue
            total += float(proceeds)
    return total, ok


def _daily_loss_limit_breached(conn, run_id: int) -> bool:
    if config.LIVE_DAILY_LOSS_LIMIT_EUR <= 0:
        return False
    midnight_utc = int(time.time() // 86400 * 86400)
    pnl, ok = _cash_flow_since(conn, run_id, midnight_utc)
    if not ok:
        print(f"[live_engine] run {run_id}: ne mogu pouzdano izračunati dnevni P&L - zaustavljam iz opreza.")
        return True
    if pnl <= -config.LIVE_DAILY_LOSS_LIMIT_EUR:
        print(f"[live_engine] run {run_id}: dnevni gubitak {pnl:.2f} EUR premašuje limit {config.LIVE_DAILY_LOSS_LIMIT_EUR} EUR.")
        return True
    return False


def _position_from_orders(conn, run_id: int) -> tuple[float, bool]:
    position = 0.0
    for order in conn.execute(
        "SELECT side, status, raw_response FROM live_order WHERE run_id=? AND status='filled' ORDER BY id", (run_id,)
    ):
        raw = json.loads(order["raw_response"] or "{}")
        filled_size = float(raw.get("filled_size", 0) or 0)
        if order["side"] == "buy":
            position += filled_size
        else:
            position = max(0.0, position - filled_size)
    return position, position > 0


def _tick(run_id: int) -> None:
    conn = db.get_connection()
    try:
        run = conn.execute(
            "SELECT * FROM paper_run WHERE id=? AND mode='live' AND status='running'", (run_id,)
        ).fetchone()
        if not run:
            return

        pair, strategy_key = run["pair"], run["strategy"]
        params = json.loads(run["params_json"])
        product_id = coinbase_client.to_product_id(pair)

        try:
            candles = coinbase_client.get_public_daily_candles(product_id, days=120)
        except Exception as err:
            print(f"[live_engine] run {run_id}: ne mogu dohvatiti svijeće ({err})")
            return
        if len(candles) < 5:
            return

        latest = candles[-1]
        if run["last_evaluated_candle_at"] == latest.opened_at:
            return

        position, in_position = _position_from_orders(conn, run_id)
        strategy = GENERIC_STRATEGIES[strategy_key]
        aux = {}
        for label in strategy.get("needs_aux", []):
            try:
                aux[label] = equity_client.fetch_recent_candles(label, days=200)
            except Exception as err:
                print(f"[live_engine] run {run_id}: ne mogu dohvatiti {label} ({err}) - preskačem ovaj tick (nema trgovanja bez makro podatka).")
                return

        series = {}
        for spec in strategy.get("needs_series", []):
            try:
                client = MACRO_CLIENTS[spec["source"]]
                series[spec["series_id"]] = client.fetch_recent(spec["series_id"], days=400)
            except Exception as err:
                print(f"[live_engine] run {run_id}: ne mogu dohvatiti {spec['series_id']} ({err}) - preskačem ovaj tick (nema trgovanja bez podatka).")
                return

        ctx = StrategyContext(candles=candles, index=len(candles) - 1, in_position=in_position, params=params, aux=aux, series=series)
        decision = strategy["decide"](ctx)

        loss_limit_breached = _daily_loss_limit_breached(conn, run_id)
        if loss_limit_breached and decision == "buy":
            conn.execute("UPDATE paper_run SET status='stopped', stopped_at=? WHERE id=?", (int(time.time()), run_id))
            conn.commit()
            return

        if decision == "buy" and not in_position:
            _check_enabled()
            quote_size = min(config.LIVE_MAX_POSITION_EUR, run["starting_balance_eur"])
            if quote_size <= 0:
                print(f"[live_engine] run {run_id}: LIVE_MAX_POSITION_EUR je 0 - nalog preskočen.")
                return
            response = coinbase_client.place_market_order(product_id, "BUY", quote_size_eur=quote_size)
            conn.execute(
                "INSERT INTO live_order (run_id, side, pair, requested_eur, coinbase_order_id, status, raw_response, created_at)"
                " VALUES (?, 'buy', ?, ?, ?, ?, ?, ?)",
                (run_id, pair, quote_size, response.get("order_id"), "filled" if response.get("success") else "error", json.dumps(response), int(time.time())),
            )
        elif decision == "sell" and in_position:
            _check_enabled()
            response = coinbase_client.place_market_order(product_id, "SELL", base_size=position)
            conn.execute(
                "INSERT INTO live_order (run_id, side, pair, requested_eur, coinbase_order_id, status, raw_response, created_at)"
                " VALUES (?, 'sell', ?, NULL, ?, ?, ?, ?)",
                (run_id, pair, response.get("order_id"), "filled" if response.get("success") else "error", json.dumps(response), int(time.time())),
            )

        conn.execute("UPDATE paper_run SET last_evaluated_candle_at=? WHERE id=?", (latest.opened_at, run_id))
        if loss_limit_breached:
            conn.execute("UPDATE paper_run SET status='stopped', stopped_at=? WHERE id=?", (int(time.time()), run_id))
        conn.commit()
    except LiveTradingDisabled as err:
        print(f"[live_engine] run {run_id}: {err}")
    finally:
        conn.close()


def _loop(run_id: int, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            _tick(run_id)
        except Exception as err:
            print(f"[live_engine] run {run_id}: neočekivana greška: {err}")
        stop_event.wait(POLL_INTERVAL_SECONDS)


def start_live_run(strategy_key: str, params: dict, pair: str) -> int:
    _check_enabled()
    if strategy_key not in GENERIC_STRATEGIES:
        raise ValueError(f"Strategija '{strategy_key}' nije podržana za live trading.")
    if config.LIVE_MAX_POSITION_EUR <= 0:
        raise ValueError("Postavi LIVE_MAX_POSITION_EUR > 0 u .env prije pokretanja live trgovanja.")

    conn = db.get_connection()
    try:
        full_params = {**GENERIC_STRATEGIES[strategy_key]["default_params"], **params}
        cur = conn.execute(
            "INSERT INTO paper_run (strategy, params_json, pair, started_at, starting_balance_eur, status, mode)"
            " VALUES (?, ?, ?, ?, ?, 'running', 'live')",
            (strategy_key, json.dumps(full_params), pair, int(time.time()), config.LIVE_MAX_POSITION_EUR),
        )
        conn.commit()
        run_id = cur.lastrowid
    finally:
        conn.close()

    stop_event = threading.Event()
    with _lock:
        _active_runs[run_id] = stop_event
    threading.Thread(target=_loop, args=(run_id, stop_event), daemon=True).start()
    return run_id


def stop_live_run(run_id: int) -> None:
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
