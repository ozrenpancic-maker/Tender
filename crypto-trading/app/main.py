import datetime
import json
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import binance_history_client, coinbase_client, config, db, equity_client, paper_engine
from app.backtest import run_backtest
from app.candles import available_pairs
from app.macro_clients import MACRO_CLIENTS, all_labels, test_all_connections
from app.optimizer import DEFAULT_GRIDS, optimize
from app.ml.dataset import HORIZONS as ML_HORIZONS
from app.ml.engine import compute_all as compute_all_predictions, compute_prediction
from app.signals import PRESETS as SIGNAL_PRESETS, compute_all as compute_all_signals
from app.strategies import GENERIC_STRATEGIES

app = FastAPI(title="Kripto trgovanje - istraživački MVP")


@app.middleware("http")
async def require_api_key(request: Request, call_next):
    """Opcionalna autentikacija (vidi config.DASHBOARD_API_KEY) - ako ključ nije postavljen u .env,
    ponašanje je nepromijenjeno (nema provjere). Ako je postavljen, svi /api/* pozivi moraju imati
    'Authorization: Bearer <ključ>'. Statika (dashboard HTML/JS) ostaje dostupna bez ključa da bi se
    stranica mogla učitati - dashboard.js sam prilaže ključ iz localStorage na svoje API pozive."""
    if config.DASHBOARD_API_KEY and request.url.path.startswith("/api/"):
        header = request.headers.get("authorization", "")
        if header != f"Bearer {config.DASHBOARD_API_KEY}":
            return JSONResponse(status_code=401, content={"detail": "Nedostaje ili je neispravan API ključ."})
    return await call_next(request)


@app.on_event("startup")
def on_startup():
    db.ensure_schema()
    paper_engine.resume_running_on_startup()


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
                "needs_series": s.get("needs_series", []),
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
    interval_min: int = 1440


@app.post("/api/backtest")
def backtest(req: BacktestRequest):
    try:
        start_ts = int(datetime.datetime.fromisoformat(req.start_date).replace(tzinfo=datetime.timezone.utc).timestamp())
        end_ts = int(datetime.datetime.fromisoformat(req.end_date).replace(tzinfo=datetime.timezone.utc).timestamp())
    except ValueError as err:
        raise HTTPException(400, f"Neispravan datum: {err}")

    conn = db.get_connection()
    try:
        result = run_backtest(
            conn, req.strategy, req.pair, start_ts, end_ts, req.params, req.starting_balance, req.interval_min
        )
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


# ---------- Optimizacija (in-sample / out-of-sample) ----------

class OptimizeRequest(BaseModel):
    strategy: str
    pair: str
    in_start_date: str
    in_end_date: str
    out_start_date: str
    out_end_date: str
    starting_balance: float = 500.0
    param_grid: dict | None = None


def _to_ts(date_str: str) -> int:
    return int(datetime.datetime.fromisoformat(date_str).replace(tzinfo=datetime.timezone.utc).timestamp())


@app.get("/api/optimize/default-grid/{strategy}")
def optimize_default_grid(strategy: str):
    grid = DEFAULT_GRIDS.get(strategy)
    if grid is None:
        raise HTTPException(404, f"Nema zadane mreže parametara za '{strategy}'.")
    return {"strategy": strategy, "param_grid": grid}


@app.post("/api/optimize")
def run_optimize(req: OptimizeRequest):
    try:
        in_start, in_end = _to_ts(req.in_start_date), _to_ts(req.in_end_date)
        out_start, out_end = _to_ts(req.out_start_date), _to_ts(req.out_end_date)
    except ValueError as err:
        raise HTTPException(400, f"Neispravan datum: {err}")

    if out_start < in_end:
        raise HTTPException(
            400,
            "Out-of-sample razdoblje mora početi nakon kraja in-sample razdoblja - inače optimizacija "
            "'vidi' podatke na kojima se naknadno provjerava, što rezultat čini beskorisnim.",
        )

    conn = db.get_connection()
    try:
        return optimize(conn, req.strategy, req.pair, in_start, in_end, out_start, out_end, req.starting_balance, req.param_grid)
    except ValueError as err:
        raise HTTPException(400, str(err))
    finally:
        conn.close()


# ---------- Makro / sentiment / fundamentalno (FRED, DeFiLlama, CoinGecko, Trends, Reddit, ETF, regulativa) ----------

@app.get("/api/macro/labels")
def macro_labels():
    return {"sources": all_labels()}


@app.get("/api/macro/test-connection")
def macro_test_connection():
    return test_all_connections()


@app.post("/api/macro/sync/{source}/{label}")
def macro_sync(source: str, label: str):
    client = MACRO_CLIENTS.get(source)
    if not client:
        raise HTTPException(400, f"Nepoznat izvor '{source}'. Dostupno: {list(MACRO_CLIENTS)}")
    conn = db.get_connection()
    try:
        count = client.sync_to_db(conn, label)
        return {"source": source, "label": label, "rows": count}
    except Exception as err:
        raise HTTPException(502, str(err))
    finally:
        conn.close()


# ---------- Binance povijest za proizvoljne parove (npr. tvoj stvarni portfolio) ----------

@app.get("/api/binance-history/pairs")
def binance_history_pairs():
    return {"pairs": list(binance_history_client.PORTFOLIO_PAIRS)}


@app.get("/api/binance-history/test-connection")
def binance_history_test_connection():
    return binance_history_client.test_connection()


class BinanceSyncRequest(BaseModel):
    pair: str
    since: str = "2017-01-01"
    interval: str = "1d"


@app.post("/api/binance-history/sync")
def binance_history_sync(req: BinanceSyncRequest):
    conn = db.get_connection()
    try:
        count = binance_history_client.sync_to_db(conn, req.pair, req.since, req.interval)
        return {"pair": req.pair, "rows": count}
    except Exception as err:
        raise HTTPException(502, str(err))
    finally:
        conn.close()


# ---------- Signali kupi/prodaj (uživo, kratkoročno + dugoročno) ----------

@app.get("/api/signals/presets")
def signals_presets():
    return {h: {"label": p["label"], "strategy": p["strategy"], "params": p["params"]} for h, p in SIGNAL_PRESETS.items()}


@app.get("/api/signals")
def signals(pairs: str = ""):
    pair_list = [p.strip() for p in pairs.split(",") if p.strip()] or list(binance_history_client.PORTFOLIO_PAIRS)
    return {"signals": compute_all_signals(pair_list)}


# ---------- AI Prediction Engine (ML, kalibrirane vjerojatnosti, 4 horizonta) ----------

@app.get("/api/predictions/horizons")
def prediction_horizons():
    import json
    from app.ml.engine import MODELS_DIR

    meta_path = MODELS_DIR / "metadata.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    return {
        h: {
            "label": spec["label"],
            "validated": meta.get(h, {}).get("validated", False),
            "trained_at": meta.get(h, {}).get("trained_at"),
            "n_examples": meta.get(h, {}).get("n_examples"),
        }
        for h, spec in ML_HORIZONS.items()
    }


@app.get("/api/predictions")
def predictions(pairs: str = ""):
    pair_list = [p.strip() for p in pairs.split(",") if p.strip()] or list(binance_history_client.PORTFOLIO_PAIRS)
    return {"predictions": compute_all_predictions(pair_list)}


@app.get("/api/predictions/{pair_a}/{pair_b}/{horizon}")
def prediction_single(pair_a: str, pair_b: str, horizon: str):
    """pair_a/pair_b jer parovi sadrže '/' (npr. BTC/USDT) - FastAPI ga ne prihvaća u jednom
    path segmentu bez posebnog pretvarača, pa je par rastavljen na dva segmenta."""
    try:
        return compute_prediction(f"{pair_a}/{pair_b}", horizon)
    except Exception as err:
        raise HTTPException(400, str(err))


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


app.mount("/", StaticFiles(directory="static", html=True), name="static")
