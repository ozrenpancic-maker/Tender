import datetime
import json
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import binance_history_client, coinbase_client, config, db, equity_client, etherscan_client, paper_engine
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
    from app import auto_trader, whale_mirror

    auto_trader.resume_running_on_startup()
    whale_mirror.resume_running_on_startup()


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
    stop_loss_pct: float | None = None  # npr. 0.08 = 8% - vidi README "Provjera savjeta o upravljanju rizikom"
    risk_pct: float | None = None  # npr. 0.01 = 1% kapitala po trgovini - treba stop_loss_pct ili atr_stop_mult
    atr_stop_mult: float | None = None  # npr. 1.5 - stop = entry - ATR*mult, umjesto fiksnog stop_loss_pct
    atr_period: int = 14
    take_profit_r_multiple: float | None = None  # npr. 3.0 = R:R 1:3 - treba definiran stop (jedan od gornja dva)
    max_consecutive_losses: int | None = None
    max_daily_drawdown_pct: float | None = None


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
            conn, req.strategy, req.pair, start_ts, end_ts, req.params, req.starting_balance, req.interval_min,
            stop_loss_pct=req.stop_loss_pct, risk_pct=req.risk_pct,
            atr_stop_mult=req.atr_stop_mult, atr_period=req.atr_period, take_profit_r_multiple=req.take_profit_r_multiple,
            max_consecutive_losses=req.max_consecutive_losses, max_daily_drawdown_pct=req.max_daily_drawdown_pct,
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


@app.get("/api/cost-scenarios")
def cost_scenarios():
    from app.costs import COST_SCENARIOS

    return {"scenarios": COST_SCENARIOS}


@app.post("/api/backtest/cost-sensitivity")
def backtest_cost_sensitivity(req: BacktestRequest):
    try:
        start_ts = int(datetime.datetime.fromisoformat(req.start_date).replace(tzinfo=datetime.timezone.utc).timestamp())
        end_ts = int(datetime.datetime.fromisoformat(req.end_date).replace(tzinfo=datetime.timezone.utc).timestamp())
    except ValueError as err:
        raise HTTPException(400, f"Neispravan datum: {err}")

    conn = db.get_connection()
    try:
        from app.backtest import run_cost_sensitivity

        return run_cost_sensitivity(
            conn, req.strategy, req.pair, start_ts, end_ts, req.params, req.starting_balance, req.interval_min
        )
    finally:
        conn.close()


# ---------- Portfelj trend strategija (više coinova, veličina po volatilnosti) ----------

class PortfolioBacktestRequest(BaseModel):
    pairs: list[str] | None = None  # None = DEFAULT_PAIRS
    strategies: list[str] | None = None  # None = DEFAULT_STRATEGIES
    start_date: str
    end_date: str
    starting_balance: float = 1000.0
    target_vol: float | None = None  # npr. 0.3 = ciljana godišnja volatilnost portfelja 30%
    rebalance_drift: float = 1.0


@app.get("/api/portfolio-backtest/defaults")
def portfolio_backtest_defaults():
    from app.portfolio_backtest import DEFAULT_PAIRS, DEFAULT_STRATEGIES, TREND_STRATEGIES, price_only_strategies

    return {
        "pairs": DEFAULT_PAIRS,
        "strategies": DEFAULT_STRATEGIES,
        "strategy_sets": {"default": DEFAULT_STRATEGIES, "all_price_only": price_only_strategies(), "trend": TREND_STRATEGIES},
    }


@app.post("/api/portfolio-backtest")
def portfolio_backtest(req: PortfolioBacktestRequest):
    from app.portfolio_backtest import (
        DEFAULT_PAIRS, DEFAULT_STRATEGIES, load_portfolio_candles, run_equal_weight_buy_hold, run_portfolio_backtest,
    )

    pairs = req.pairs or DEFAULT_PAIRS
    strategies = req.strategies or DEFAULT_STRATEGIES
    unknown = [s for s in strategies if s not in GENERIC_STRATEGIES]
    if unknown:
        raise HTTPException(400, f"Nepoznate strategije: {', '.join(unknown)}")
    needs_extra = [s for s in strategies if GENERIC_STRATEGIES[s].get("needs_aux") or GENERIC_STRATEGIES[s].get("needs_series")]
    if needs_extra:
        raise HTTPException(400, f"Portfelj podržava samo čisto cjenovne strategije, ne: {', '.join(needs_extra)}")
    if not 1 <= len(pairs) <= 10:
        raise HTTPException(400, "Odaberi 1 do 10 parova.")
    if req.target_vol is not None and not 0.05 <= req.target_vol <= 3:
        raise HTTPException(400, "target_vol mora biti između 0.05 i 3 (5% - 300% godišnje).")
    if req.starting_balance <= 0 or req.rebalance_drift <= 0:
        raise HTTPException(400, "starting_balance i rebalance_drift moraju biti pozitivni.")
    try:
        start_ts, end_ts = _to_ts(req.start_date), _to_ts(req.end_date)
    except ValueError as err:
        raise HTTPException(400, f"Neispravan datum: {err}")
    if end_ts <= start_ts:
        raise HTTPException(400, "Završni datum mora biti nakon početnog.")

    conn = db.get_connection()
    try:
        cbp = load_portfolio_candles(conn, pairs, start_ts, end_ts)
        portfolio = run_portfolio_backtest(
            cbp, strategies, req.starting_balance, start_ts, target_vol=req.target_vol, rebalance_drift=req.rebalance_drift,
        )
        buy_hold = run_equal_weight_buy_hold(cbp, req.starting_balance, start_ts)
        return {"portfolio": portfolio, "buy_hold": buy_hold}
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


@app.get("/api/predictions/retrain-log")
def prediction_retrain_log():
    from app.ml.retrain_scheduled import read_log

    return {"log": read_log()}


@app.post("/api/predictions/retrain-now")
def prediction_retrain_now():
    """Ručno okini isto ono što tjedni Windows Task Scheduler zadatak radi - koristan za test
    postavljanja prije nego se pouzda u automatiku (vidi README 'Automatsko ponovno treniranje').
    Ovo stvarno trenira (desetke sekundi do par minuta) - NIJE instant, zato zaseban gumb, ne dio
    normalnog osvježavanja dashboarda."""
    from app.ml.retrain_scheduled import run

    try:
        return run()
    except Exception as err:
        raise HTTPException(500, f"Ponovno treniranje nije uspjelo: {err}")


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
    interval_min: int = 1440  # 60 = satne svijeće (više trgovina dnevno), 1440 = dnevne (zadano)
    execution_mode: str = "taker"  # "taker" (odmah, pravi bid/ask+fee) ili "maker_post_only" (čeka ispunjenje)
    daily_loss_limit_pct: float | None = None  # npr. 0.05 = 5% - prisilan izlaz + pauza do sutra ako probijeno


@app.post("/api/paper/start")
def paper_start(req: StartRunRequest):
    try:
        run_id = paper_engine.start_run(
            req.strategy, req.params, req.pair, req.starting_balance, req.interval_min,
            req.execution_mode, req.daily_loss_limit_pct,
        )
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


@app.get("/api/paper/export-csv")
def paper_export_csv_all():
    """SIMULIRAN dnevnik transakcija (vježba FIFO knjigovodstva) preko SVIH paper trading runova -
    NIJE prava porezna evidencija, nema stvarne kapitalne dobiti jer nema pravog novca. Registrirano
    PRIJE /api/paper/{run_id} - FastAPI bira rutu po redoslijedu registracije, a /api/paper/{run_id}
    bi inače "export-csv" pokušao parsirati kao run_id."""
    csv_text = paper_engine.export_trades_csv()
    return PlainTextResponse(csv_text, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=paper_trading_dnevnik_SIMULACIJA.csv"})


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


@app.get("/api/paper/{run_id}/export-csv")
def paper_export_csv_one(run_id: int):
    csv_text = paper_engine.export_trades_csv(run_id)
    return PlainTextResponse(csv_text, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=paper_run_{run_id}_SIMULACIJA.csv"})


# ---------- Automatizirani multi-coin paper trading (AI bira coin) ----------

class AutoTraderStartRequest(BaseModel):
    horizon: str  # '1h' ili '4h' - samo validirani horizonti
    universe: list[str] = []  # prazno = korisnikov portfolio (PORTFOLIO_PAIRS)
    starting_balance: float = 1000.0
    max_position_pct: float = 0.2  # 20% budžeta po coinu
    trade_mode: str = "scalp"  # "scalp" (zadano) ili "swing" (drži kroz manje oscilacije)
    min_hold_periods: int = 1  # samo za swing - min. broj horizont-perioda prije AI-signal izlaska
    take_profit_pct: float | None = None  # samo za swing, npr. 0.05 = 5%
    stop_loss_pct: float | None = None  # samo za swing, npr. 0.05 = 5% - radi uvijek, čak i prije min_hold_periods


@app.post("/api/auto-trader/start")
def auto_trader_start(req: AutoTraderStartRequest):
    from app import auto_trader
    from app.ml.engine import is_horizon_validated

    if not is_horizon_validated(req.horizon):
        raise HTTPException(
            400,
            f"Horizont '{req.horizon}' trenutno nije validiran (vidi odjeljak 1, AI Prediction "
            f"Engine) - automatizirani trading se ne pokreće na nevalidiranom modelu.",
        )
    universe = req.universe or list(binance_history_client.PORTFOLIO_PAIRS)
    try:
        run_id = auto_trader.start_run(
            req.horizon, universe, req.starting_balance, req.max_position_pct,
            req.trade_mode, req.min_hold_periods, req.take_profit_pct, req.stop_loss_pct,
        )
        return {"run_id": run_id}
    except ValueError as err:
        raise HTTPException(400, str(err))


@app.post("/api/auto-trader/{run_id}/stop")
def auto_trader_stop(run_id: int):
    from app import auto_trader

    auto_trader.stop_run(run_id)
    return {"ok": True}


@app.get("/api/auto-trader/runs")
def auto_trader_runs():
    conn = db.get_connection()
    try:
        rows = conn.execute("SELECT * FROM auto_trader_run ORDER BY started_at DESC").fetchall()
        runs = []
        for r in rows:
            run = dict(r)
            last_point = conn.execute(
                "SELECT equity_eur, at FROM auto_trader_equity_point WHERE run_id=? ORDER BY at DESC LIMIT 1", (run["id"],)
            ).fetchone()
            run["current_equity_eur"] = last_point["equity_eur"] if last_point else run["starting_balance_eur"]
            run["last_update_at"] = last_point["at"] if last_point else None
            run["open_positions"] = conn.execute(
                "SELECT COUNT(*) AS n FROM auto_trader_position WHERE run_id=? AND closed_at IS NULL", (run["id"],)
            ).fetchone()["n"]
            runs.append(run)
        return {"runs": runs}
    finally:
        conn.close()


@app.get("/api/auto-trader/export-csv")
def auto_trader_export_csv_all():
    from app import auto_trader

    csv_text = auto_trader.export_trades_csv()
    return PlainTextResponse(csv_text, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=auto_trader_SVI_RUNOVI_SIMULACIJA.csv"})


@app.get("/api/auto-trader/{run_id}")
def auto_trader_detail(run_id: int):
    conn = db.get_connection()
    try:
        run = conn.execute("SELECT * FROM auto_trader_run WHERE id=?", (run_id,)).fetchone()
        if not run:
            raise HTTPException(404, "Run nije pronađen.")
        trades = conn.execute("SELECT * FROM auto_trader_trade WHERE run_id=? ORDER BY executed_at", (run_id,)).fetchall()
        positions = conn.execute("SELECT * FROM auto_trader_position WHERE run_id=? ORDER BY opened_at", (run_id,)).fetchall()
        equity = conn.execute("SELECT * FROM auto_trader_equity_point WHERE run_id=? ORDER BY at", (run_id,)).fetchall()
        return {
            "run": dict(run),
            "trades": [dict(t) for t in trades],
            "positions": [dict(p) for p in positions],
            "equity_curve": [dict(e) for e in equity],
        }
    finally:
        conn.close()


@app.get("/api/auto-trader/{run_id}/export-csv")
def auto_trader_export_csv_one(run_id: int):
    from app import auto_trader

    csv_text = auto_trader.export_trades_csv(run_id)
    return PlainTextResponse(csv_text, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=auto_trader_run_{run_id}_SIMULACIJA.csv"})


# ---------- Whale mirror (zrcali javni on-chain novčanik, UŽIVO, bez backtesta) ----------

class WhaleMirrorStartRequest(BaseModel):
    label: str = "Ethereum Foundation"
    address: str = "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe"
    pair: str = "ETH/USDT"
    starting_balance: float = 100.0
    threshold_pct: float = 0.03  # 3% promjene stanja novčanika da se okine trgovina


@app.post("/api/whale-mirror/start")
def whale_mirror_start(req: WhaleMirrorStartRequest):
    from app import whale_mirror

    try:
        run_id = whale_mirror.start_run(req.label, req.address, req.pair, req.starting_balance, req.threshold_pct)
        return {"run_id": run_id}
    except (ValueError, etherscan_client.EtherscanError) as err:
        raise HTTPException(400, str(err))


@app.post("/api/whale-mirror/{run_id}/stop")
def whale_mirror_stop(run_id: int):
    from app import whale_mirror

    whale_mirror.stop_run(run_id)
    return {"ok": True}


@app.get("/api/whale-mirror/runs")
def whale_mirror_runs():
    conn = db.get_connection()
    try:
        rows = conn.execute("SELECT * FROM whale_mirror_run ORDER BY started_at DESC").fetchall()
        runs = []
        for r in rows:
            run = dict(r)
            last_point = conn.execute(
                "SELECT equity, at FROM whale_mirror_equity_point WHERE run_id=? ORDER BY at DESC LIMIT 1", (run["id"],)
            ).fetchone()
            run["current_equity"] = last_point["equity"] if last_point else run["starting_balance"]
            run["last_update_at"] = last_point["at"] if last_point else None
            runs.append(run)
        return {"runs": runs}
    finally:
        conn.close()


@app.get("/api/whale-mirror/test-connection")
def whale_mirror_test_connection():
    try:
        return etherscan_client.test_connection()
    except etherscan_client.EtherscanError as err:
        raise HTTPException(400, str(err))


@app.get("/api/whale-mirror/export-csv")
def whale_mirror_export_csv_all():
    from app import whale_mirror

    csv_text = whale_mirror.export_trades_csv()
    return PlainTextResponse(csv_text, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=whale_mirror_SVI_RUNOVI_SIMULACIJA.csv"})


@app.get("/api/whale-mirror/{run_id}")
def whale_mirror_detail(run_id: int):
    conn = db.get_connection()
    try:
        run = conn.execute("SELECT * FROM whale_mirror_run WHERE id=?", (run_id,)).fetchone()
        if not run:
            raise HTTPException(404, "Run nije pronađen.")
        trades = conn.execute("SELECT * FROM whale_mirror_trade WHERE run_id=? ORDER BY executed_at", (run_id,)).fetchall()
        equity = conn.execute("SELECT * FROM whale_mirror_equity_point WHERE run_id=? ORDER BY at", (run_id,)).fetchall()
        return {"run": dict(run), "trades": [dict(t) for t in trades], "equity_curve": [dict(e) for e in equity]}
    finally:
        conn.close()


@app.get("/api/whale-mirror/{run_id}/export-csv")
def whale_mirror_export_csv_one(run_id: int):
    from app import whale_mirror

    csv_text = whale_mirror.export_trades_csv(run_id)
    return PlainTextResponse(csv_text, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=whale_mirror_run_{run_id}_SIMULACIJA.csv"})


def _run_summary(conn, run: dict) -> dict:
    last_point = conn.execute(
        "SELECT equity_eur, at FROM paper_equity_point WHERE run_id=? AND equity_eur >= 0 ORDER BY at DESC LIMIT 1",
        (run["id"],),
    ).fetchone()
    run["current_equity_eur"] = last_point["equity_eur"] if last_point else run["starting_balance_eur"]
    run["last_update_at"] = last_point["at"] if last_point else None
    return run


app.mount("/", StaticFiles(directory="static", html=True), name="static")
