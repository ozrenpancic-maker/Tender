import datetime
import json
import time

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import coinbase_client, config, db, equity_client, live_engine, paper_engine
from app.backtest import run_backtest
from app.candles import available_pairs
from app.strategies import GENERIC_STRATEGIES

app = FastAPI(title="Kripto trgovanje - istraživački MVP")


@app.on_event("startup")
def on_startup():
    db.ensure_schema()
    paper_engine.resume_running_on_startup()
    # Live runovi se NAMJERNO ne nastavljaju automatski nakon restarta servera - vidi README.


# ---------- Strategije / parovi ----------

@app.get("/api/strategies")
def list_strategies():
    items = [
        {"key": "buy_hold", "label": "Buy & hold (referentna točka)", "default_params": {}, "backtest_only": True},
        {
            "key": "baseline_2pct",
            "label": "Bazno pravilo iz priloženog izvještaja (gubi novac - referenca)",
            "default_params": {},
            "backtest_only": True,
        },
    ]
    for key, s in GENERIC_STRATEGIES.items():
        items.append(
            {
                "key": key,
                "label": s["label"],
                "default_params": s["default_params"],
                "backtest_only": False,
                "needs_aux": s.get("needs_aux", []),
            }
        )
    return {"strategies": items}


@app.get("/api/pairs")
def list_pairs():
    conn = db.get_connection()
    try:
        return {"pairs": available_pairs(conn)}
    finally:
        conn.close()


# ---------- Backtest ----------

class BacktestRequest(BaseModel):
    strategy: str
    pair: str
    start_date: str  # YYYY-MM-DD
    end_date: str
    params: dict = {}
    starting_balance: float = 500.0


@app.post("/api/backtest")
def backtest(req: BacktestRequest):
    try:
        start_ts = int(datetime.datetime.fromisoformat(req.start_date).replace(tzinfo=datetime.timezone.utc).timestamp())
        end_ts = int(datetime.datetime.fromisoformat(req.end_date).replace(tzinfo=datetime.timezone.utc).timestamp())
    except ValueError as err:
        raise HTTPException(400, f"Neispravan datum: {err}")

    conn = db.get_connection()
    try:
        result = run_backtest(conn, req.strategy, req.pair, start_ts, end_ts, req.params, req.starting_balance)
        conn.execute(
            "INSERT INTO backtest_run (strategy, params_json, pair, start_date, end_date, result_json, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (req.strategy, json.dumps(req.params), req.pair, req.start_date, req.end_date, json.dumps(result), int(time.time())),
        )
        conn.commit()
        return result
    except ValueError as err:
        raise HTTPException(400, str(err))
    finally:
        conn.close()


# ---------- Wall Street / equity indeksi ----------

@app.get("/api/equity/test-connection")
def equity_test_connection():
    return equity_client.test_connection()


@app.post("/api/equity/sync/{label}")
def equity_sync(label: str):
    if label not in equity_client.INDEX_SYMBOLS:
        raise HTTPException(400, f"Nepoznata oznaka '{label}'. Dostupno: {list(equity_client.INDEX_SYMBOLS)}")
    conn = db.get_connection()
    try:
        count = equity_client.sync_to_db(conn, label)
        return {"label": label, "rows": count}
    except equity_client.EquityError as err:
        raise HTTPException(502, str(err))
    finally:
        conn.close()


@app.get("/api/equity/labels")
def equity_labels():
    return {"labels": list(equity_client.INDEX_SYMBOLS)}


# ---------- Coinbase ----------

@app.get("/api/coinbase/test-connection")
def coinbase_test_connection():
    return coinbase_client.test_connection()


# ---------- Paper trading ----------

class StartRunRequest(BaseModel):
    strategy: str
    pair: str
    params: dict = {}
    starting_balance: float = 500.0


@app.post("/api/paper/start")
def paper_start(req: StartRunRequest):
    try:
        run_id = paper_engine.start_run(req.strategy, req.params, req.pair, req.starting_balance)
        return {"run_id": run_id}
    except ValueError as err:
        raise HTTPException(400, str(err))


@app.post("/api/paper/{run_id}/stop")
def paper_stop(run_id: int):
    paper_engine.stop_run(run_id)
    return {"ok": True}


@app.get("/api/paper/runs")
def paper_runs():
    conn = db.get_connection()
    try:
        rows = conn.execute("SELECT * FROM paper_run WHERE mode='paper' ORDER BY started_at DESC").fetchall()
        return {"runs": [_run_summary(conn, dict(r)) for r in rows]}
    finally:
        conn.close()


@app.get("/api/paper/{run_id}")
def paper_detail(run_id: int):
    conn = db.get_connection()
    try:
        run = conn.execute("SELECT * FROM paper_run WHERE id=? AND mode='paper'", (run_id,)).fetchone()
        if not run:
            raise HTTPException(404, "Run nije pronađen.")
        trades = conn.execute("SELECT * FROM paper_trade WHERE run_id=? ORDER BY executed_at", (run_id,)).fetchall()
        equity = conn.execute(
            "SELECT * FROM paper_equity_point WHERE run_id=? AND equity_eur >= 0 ORDER BY at", (run_id,)
        ).fetchall()
        return {"run": dict(run), "trades": [dict(t) for t in trades], "equity_curve": [dict(e) for e in equity]}
    finally:
        conn.close()


def _run_summary(conn, run: dict) -> dict:
    last_point = conn.execute(
        "SELECT equity_eur, at FROM paper_equity_point WHERE run_id=? AND equity_eur >= 0 ORDER BY at DESC LIMIT 1",
        (run["id"],),
    ).fetchone()
    run["current_equity_eur"] = last_point["equity_eur"] if last_point else run["starting_balance_eur"]
    run["last_update_at"] = last_point["at"] if last_point else None
    return run


# ---------- Live trading (isključeno po defaultu - vidi README) ----------

@app.get("/api/live/status")
def live_status():
    return {
        "enabled": config.LIVE_TRADING_ENABLED,
        "max_position_eur": config.LIVE_MAX_POSITION_EUR,
        "daily_loss_limit_eur": config.LIVE_DAILY_LOSS_LIMIT_EUR,
    }


@app.post("/api/live/start")
def live_start(req: StartRunRequest):
    try:
        run_id = live_engine.start_live_run(req.strategy, req.params, req.pair)
        return {"run_id": run_id}
    except (ValueError, live_engine.LiveTradingDisabled) as err:
        raise HTTPException(400, str(err))


@app.post("/api/live/{run_id}/stop")
def live_stop(run_id: int):
    live_engine.stop_live_run(run_id)
    return {"ok": True}


@app.get("/api/live/runs")
def live_runs():
    conn = db.get_connection()
    try:
        rows = conn.execute("SELECT * FROM paper_run WHERE mode='live' ORDER BY started_at DESC").fetchall()
        return {"runs": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.get("/api/live/{run_id}")
def live_detail(run_id: int):
    conn = db.get_connection()
    try:
        run = conn.execute("SELECT * FROM paper_run WHERE id=? AND mode='live'", (run_id,)).fetchone()
        if not run:
            raise HTTPException(404, "Run nije pronađen.")
        orders = conn.execute("SELECT * FROM live_order WHERE run_id=? ORDER BY created_at", (run_id,)).fetchall()
        return {"run": dict(run), "orders": [dict(o) for o in orders]}
    finally:
        conn.close()


app.mount("/", StaticFiles(directory="static", html=True), name="static")
