"""Automatizirani multi-coin PAPER trading: AI Prediction Engine (app/ml/engine.py) SAM BIRA koji
coin kupiti/prodati, unutar ograničenog virtualnog budžeta, provjeravano svaki sat/4h ovisno o
horizontu - "trguje više puta dnevno" po potrebi (ne na silu, samo kad postoji stvaran signal).

I OVO JE I DALJE SIMULACIJA - bez pravog novca, bez Coinbase trgovačkih API ključeva (KriptoMVP 4.4
pravilo #2/#3). "Automatizirano" znači autonomna ODLUKA unutar simulacije, ne pravi nalog. Vidi
README "Automatizirani paper trading" za potpuno objašnjenje i zašto NE postoji pandan za pravi
novac u ovom projektu.

Koristi SAMO validirane horizonte (1h/4h - vidi data/models/metadata.json). Ako horizont prestane
biti validiran nakon ponovnog treniranja, run se automatski zaustavlja umjesto da nastavi "trgovati"
na nevalidiranom modelu. 24h/7d NISU validirani (provjereno uživo: 24h Brier 0.51349 vs bazna
0.51368 - ispod praga poboljšanja; 7d jasno gori od bazne linije) - "swing" način rada ispod i dalje
koristi SAMO 1h/4h signal, ne te horizonte (vidi README "Swing način rada" za potpuno objašnjenje).

DVA NAČINA RADA (`trade_mode`):
- "scalp" (zadano, dosadašnje ponašanje): zatvara poziciju ČIM AI signal za taj coin padne na
  SELL/STRONG SELL, bez minimalnog vremena držanja ni fiksnog profit cilja/stop-lossa.
- "swing": drži poziciju KROZ manje oscilacije (ne reagira na svaki pad AI Score-a) dok ne prođe
  `min_hold_periods` horizont-perioda OD ULASKA, a izlazi prije toga SAMO na stop-loss (sigurnosni
  izlaz uvijek radi, čak i prije isteka minimalnog držanja). Nakon proteka minimalnog razdoblja,
  izlazi na AI SELL/STRONG SELL signal ILI na dosegnut profit cilj, što prije nastupi.
"""
import json
import threading
import time

from app import coinbase_client, db
from app.costs import TAKER_FEE, taker_buy_fill, taker_sell_fill
from app.ml.engine import compute_prediction, is_horizon_validated

POLL_INTERVAL_SECONDS = 300  # provjera svakih 5 min; stvarna odluka samo na granici horizont-perioda
HORIZON_SECONDS = {"1h": 3600, "4h": 14400}
BUY_CATEGORIES = {"BUY", "STRONG BUY"}
SELL_CATEGORIES = {"SELL", "STRONG SELL"}

_active_runs: dict[int, threading.Event] = {}
_lock = threading.Lock()


def _max_position_eur(run: dict) -> float:
    return run["starting_balance_eur"] * run["max_position_pct"]


def _max_concurrent(run: dict) -> int:
    return max(1, int(1 / run["max_position_pct"]))


def _open_positions(conn, run_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM auto_trader_position WHERE run_id=? AND closed_at IS NULL", (run_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def _tick(run_id: int) -> None:
    conn = db.get_connection()
    try:
        run_row = conn.execute("SELECT * FROM auto_trader_run WHERE id=? AND status='running'", (run_id,)).fetchone()
        if not run_row:
            return
        run = dict(run_row)
        horizon = run["horizon"]
        if horizon not in HORIZON_SECONDS:
            print(f"[auto_trader] run {run_id}: nepoznat horizont '{horizon}' - zaustavljam.")
            stop_run(run_id)
            return

        bucket_seconds = HORIZON_SECONDS[horizon]
        now = int(time.time())
        current_bucket = (now // bucket_seconds) * bucket_seconds

        # Equity point se bilježi na SVAKI tick (čak i bez nove odluke) - za glatku krivulju.
        open_positions = _open_positions(conn, run_id)
        universe = json.loads(run["universe_json"])
        mark_value = 0.0
        for pos in open_positions:
            try:
                ticker = coinbase_client.get_public_ticker(coinbase_client.to_product_id(pos["pair"]))
                mark_value += pos["quantity_base"] * taker_sell_fill(ticker["bid"]) * (1 - TAKER_FEE)
            except Exception as err:
                print(f"[auto_trader] run {run_id}: ne mogu dohvatiti cijenu za {pos['pair']} ({err}) - zadržavam zadnju procjenu.")
                mark_value += pos["entry_eur"]  # konzervativna zamjena ako cijena trenutno nedostupna
        equity = run["cash_eur"] + mark_value
        conn.execute(
            "INSERT OR REPLACE INTO auto_trader_equity_point (run_id, at, equity_eur, cash_eur, open_positions) VALUES (?, ?, ?, ?, ?)",
            (run_id, now, round(equity, 4), round(run["cash_eur"], 4), len(open_positions)),
        )
        conn.commit()

        if current_bucket <= run["last_tick_bucket"]:
            return  # unutar istog horizont-perioda kao zadnja odluka - ništa novo za odlučiti

        # Pouzdanost modela se provjerava SVAKI tick (ne samo pri pokretanju, i NE iz keša) - ako
        # naknadno ponovno treniranje makne validaciju za ovaj horizont, run se zaustavlja umjesto
        # da nastavi "trgovati" na modelu koji više ne prolazi walk-forward provjeru.
        if not is_horizon_validated(horizon):
            print(f"[auto_trader] run {run_id}: horizont '{horizon}' više nije validiran - zaustavljam run.")
            stop_run(run_id)
            return

        predictions = {}
        for pair in universe:
            try:
                pred = compute_prediction(pair, horizon)
            except Exception as err:
                print(f"[auto_trader] run {run_id}: predikcija za {pair} nije uspjela ({err}) - preskačem par ovaj tick.")
                continue
            if pred.get("ai_score") is None:
                continue  # zastarjeli podaci ili nedovoljno svijeća za OVAJ par - preskoči, ne zaustavljaj cijeli run
            predictions[pair] = pred

        open_positions = _open_positions(conn, run_id)
        held_pairs = {p["pair"] for p in open_positions}
        cash = run["cash_eur"]

        # 1) Izlasci prvo - oslobodi gotovinu prije eventualnih novih ulazaka.
        trade_mode = run["trade_mode"]
        for pos in open_positions:
            pred = predictions.get(pos["pair"])
            try:
                ticker = coinbase_client.get_public_ticker(coinbase_client.to_product_id(pos["pair"]))
            except Exception as err:
                print(f"[auto_trader] run {run_id}: ne mogu provjeriti/prodati {pos['pair']} ({err}) - pokušat ću sljedeći tick.")
                continue

            exit_reason = None
            if trade_mode == "swing":
                held_periods = (now - pos["opened_at"]) // bucket_seconds
                gain = ticker["bid"] / pos["entry_price"] - 1
                stop_loss_pct = run["stop_loss_pct"]
                take_profit_pct = run["take_profit_pct"]
                if stop_loss_pct and gain <= -stop_loss_pct:
                    exit_reason = "swing stop-loss"
                elif held_periods >= run["min_hold_periods"]:
                    if take_profit_pct and gain >= take_profit_pct:
                        exit_reason = "swing profit cilj"
                    elif pred and pred["decision"] in SELL_CATEGORIES:
                        exit_reason = "AI signal (nakon min. držanja)"
                # ispod min_hold_periods i bez probijenog stop-lossa - DRŽI kroz manju oscilaciju,
                # ne reagira na svaki pad AI Score-a (to je bit "swing" načina rada)
            else:  # "scalp" - dosadašnje ponašanje, bez minimalnog držanja ni TP/SL
                if pred and pred["decision"] in SELL_CATEGORIES:
                    exit_reason = "AI signal"

            if exit_reason is None:
                continue

            fill = taker_sell_fill(ticker["bid"])
            proceeds = pos["quantity_base"] * fill * (1 - TAKER_FEE)
            cash += proceeds
            conn.execute(
                "UPDATE auto_trader_position SET closed_at=?, exit_price=?, exit_eur=? WHERE id=?",
                (now, fill, round(proceeds, 4), pos["id"]),
            )
            decision_label = pred["decision"] if pred else exit_reason
            ai_score = pred["ai_score"] if pred else None
            conn.execute(
                "INSERT INTO auto_trader_trade (run_id, pair, side, price, amount_eur, ai_score, decision, executed_at)"
                " VALUES (?, ?, 'sell', ?, ?, ?, ?, ?)",
                (run_id, pos["pair"], fill, round(proceeds, 4), ai_score, f"{decision_label} ({exit_reason})", now),
            )
            held_pairs.discard(pos["pair"])

        # 2) Ulasci - rangiraj kandidate po AI Score-u, uđi redom dok ima gotovine i slobodnih mjesta.
        max_position_eur = _max_position_eur(run)
        max_concurrent = _max_concurrent(run)
        candidates = [
            (pair, pred) for pair, pred in predictions.items()
            if pair not in held_pairs and pred["decision"] in BUY_CATEGORIES
        ]
        candidates.sort(key=lambda item: item[1]["ai_score"], reverse=True)

        for pair, pred in candidates:
            if len(held_pairs) >= max_concurrent:
                break
            amount_eur = min(max_position_eur, cash)
            if amount_eur < 1.0:  # premalo da ima smisla (naknade bi pojele poziciju)
                break
            try:
                ticker = coinbase_client.get_public_ticker(coinbase_client.to_product_id(pair))
            except Exception as err:
                print(f"[auto_trader] run {run_id}: ne mogu kupiti {pair} ({err}) - preskačem.")
                continue
            fill = taker_buy_fill(ticker["ask"])
            quantity = (amount_eur * (1 - TAKER_FEE)) / fill
            cash -= amount_eur
            conn.execute(
                "INSERT INTO auto_trader_position (run_id, pair, quantity_base, entry_price, entry_eur, opened_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, pair, quantity, fill, amount_eur, now),
            )
            conn.execute(
                "INSERT INTO auto_trader_trade (run_id, pair, side, price, amount_eur, ai_score, decision, executed_at)"
                " VALUES (?, ?, 'buy', ?, ?, ?, ?, ?)",
                (run_id, pair, fill, amount_eur, pred["ai_score"], pred["decision"], now),
            )
            held_pairs.add(pair)

        conn.execute(
            "UPDATE auto_trader_run SET cash_eur=?, last_tick_bucket=? WHERE id=?",
            (round(cash, 4), current_bucket, run_id),
        )
        conn.commit()
    finally:
        conn.close()


def _loop(run_id: int, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            _tick(run_id)
        except Exception as err:  # auto-trader ne smije srušiti server zbog privremene greške
            print(f"[auto_trader] run {run_id}: neočekivana greška: {err}")
        stop_event.wait(POLL_INTERVAL_SECONDS)


VALID_TRADE_MODES = {"scalp", "swing"}


def start_run(
    horizon: str, universe: list[str], starting_balance: float, max_position_pct: float,
    trade_mode: str = "scalp", min_hold_periods: int = 1,
    take_profit_pct: float | None = None, stop_loss_pct: float | None = None,
) -> int:
    if horizon not in HORIZON_SECONDS:
        raise ValueError(f"Nepodržan horizont '{horizon}'. Dostupno: {list(HORIZON_SECONDS)}")
    if not 0 < max_position_pct <= 1:
        raise ValueError("max_position_pct mora biti između 0 i 1 (npr. 0.2 = 20%).")
    if not universe:
        raise ValueError("Univerzum parova ne smije biti prazan.")
    if trade_mode not in VALID_TRADE_MODES:
        raise ValueError(f"Nepodržan trade_mode '{trade_mode}'. Dostupno: {sorted(VALID_TRADE_MODES)}")
    if trade_mode == "swing":
        if min_hold_periods < 1:
            raise ValueError("min_hold_periods mora biti barem 1 za swing način rada.")
        if take_profit_pct is not None and not 0 < take_profit_pct < 2:
            raise ValueError("take_profit_pct mora biti između 0 i 2 (npr. 0.05 = 5%).")
        if stop_loss_pct is not None and not 0 < stop_loss_pct < 1:
            raise ValueError("stop_loss_pct mora biti između 0 i 1 (npr. 0.05 = 5%).")

    conn = db.get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO auto_trader_run (horizon, universe_json, starting_balance_eur, max_position_pct, started_at,"
            " status, cash_eur, trade_mode, min_hold_periods, take_profit_pct, stop_loss_pct)"
            " VALUES (?, ?, ?, ?, ?, 'running', ?, ?, ?, ?, ?)",
            (
                horizon, json.dumps(universe), starting_balance, max_position_pct, int(time.time()), starting_balance,
                trade_mode, min_hold_periods, take_profit_pct, stop_loss_pct,
            ),
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


def stop_run(run_id: int) -> None:
    with _lock:
        stop_event = _active_runs.pop(run_id, None)
    if stop_event:
        stop_event.set()
    conn = db.get_connection()
    try:
        conn.execute("UPDATE auto_trader_run SET status='stopped', stopped_at=? WHERE id=?", (int(time.time()), run_id))
        conn.commit()
    finally:
        conn.close()


def resume_running_on_startup() -> None:
    conn = db.get_connection()
    try:
        rows = conn.execute("SELECT id FROM auto_trader_run WHERE status='running'").fetchall()
    finally:
        conn.close()
    for row in rows:
        stop_event = threading.Event()
        with _lock:
            _active_runs[row["id"]] = stop_event
        threading.Thread(target=_loop, args=(row["id"], stop_event), daemon=True).start()
