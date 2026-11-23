"""Pretraga parametara strategije UZ provjeru izvan uzorka (out-of-sample).

Zašto ovo postoji: biranje parametara koji daju najbolji rezultat na JEDNOM povijesnom razdoblju je
"curve fitting" - gotovo uvijek se može naći neka kombinacija koja na papiru izgleda odlično, bez
ikakve stvarne prednosti (slučajnost se preklopila s parametrima). Jedini djelomičan lijek je:
1. Pretraži parametre na "in-sample" razdoblju (npr. 2024-2025).
2. Uzmi par najboljih kombinacija i provjeri ih na "out-of-sample" razdoblju koje optimizacija
   NIJE vidjela (npr. 2026. do danas).
3. Vjeruj samo onome što radi dobro na OBA razdoblja - a i tada s oprezom, jer dvije točke podataka
   (dva razdoblja) i dalje nisu jamstvo da će strategija raditi u budućnosti.
"""
import itertools

from app.backtest import run_backtest

DEFAULT_GRIDS: dict[str, dict[str, list]] = {
    "sma_crossover": {"fast": [5, 8, 10, 15, 20], "slow": [20, 30, 40, 50, 60]},
    "rsi_meanrev": {"period": [7, 14, 21], "buy_below": [20, 25, 30, 35], "sell_above": [55, 60, 65, 70]},
    "dip_buy_volume": {"drop_pct": [0.015, 0.02, 0.03], "volume_mult": [1.2, 1.5, 2.0], "hold_days": [1, 3, 5, 7]},
    "equity_filtered": {"fast": [5, 10, 15], "slow": [20, 30, 50], "spx_sma": [20, 50, 100]},
    "multi_macro_filter": {
        "fast": [5, 10, 15],
        "slow": [20, 30, 50],
        "spx_sma": [20, 50],
        "gold_sma": [20, 50],
        "gold_spike_pct": [0.03, 0.05, 0.08],
    },
    "technical_composite": {
        "ema_trend": [100, 150, 200],
        "macd_fast": [8, 12],
        "macd_slow": [21, 26],
        "obv_lookback": [5, 10, 20],
        "require_obv_confirm": [True, False],
    },
    "macro_signal_composite": {
        "ema_trend": [100, 150, 200],
        "min_risk_on_votes": [2, 3, 4],
        "fed_lookback": [1, 3, 6],
    },
    "derivatives_extremes": {
        "extreme_negative": [-0.001, -0.0007, -0.0005, -0.0003],
        "extreme_positive": [0.0003, 0.0005, 0.0007, 0.001],
        "lookback_days": [1, 3, 5],
        "hold_days": [3, 5, 7, 10],
    },
}

MAX_COMBINATIONS = 400
TOP_N_FOR_OUT_OF_SAMPLE = 5


def _param_combinations(grid: dict[str, list]) -> list[dict]:
    keys = list(grid.keys())
    combos = [dict(zip(keys, values)) for values in itertools.product(*grid.values())]
    if len(combos) > MAX_COMBINATIONS:
        raise ValueError(
            f"Mreža parametara ima {len(combos)} kombinacija, limit je {MAX_COMBINATIONS}. Suzi raspon."
        )
    return combos


def optimize(
    conn,
    strategy_key: str,
    pair: str,
    in_start_ts: int,
    in_end_ts: int,
    out_start_ts: int,
    out_end_ts: int,
    starting_balance: float,
    param_grid: dict[str, list] | None = None,
) -> dict:
    grid = param_grid or DEFAULT_GRIDS.get(strategy_key)
    if not grid:
        raise ValueError(f"Nema zadane mreže parametara za '{strategy_key}' - proslijedi param_grid ručno.")

    combos = _param_combinations(grid)

    in_sample_results = []
    for params in combos:
        try:
            r = run_backtest(conn, strategy_key, pair, in_start_ts, in_end_ts, params, starting_balance)
        except ValueError:
            continue
        in_sample_results.append(
            {
                "params": params,
                "in_sample": {
                    "final_balance": r["final_balance"],
                    "trades": r["trades"],
                    "winning_trades": r["winning_trades"],
                    "max_drawdown_pct": r["max_drawdown_pct"],
                },
            }
        )

    if not in_sample_results:
        raise ValueError("Nijedna kombinacija parametara nije dala rezultat na in-sample razdoblju (nedostaju podaci?).")

    in_sample_results.sort(key=lambda r: r["in_sample"]["final_balance"], reverse=True)
    top = in_sample_results[:TOP_N_FOR_OUT_OF_SAMPLE]

    for entry in top:
        try:
            r = run_backtest(conn, strategy_key, pair, out_start_ts, out_end_ts, entry["params"], starting_balance)
            entry["out_of_sample"] = {
                "final_balance": r["final_balance"],
                "trades": r["trades"],
                "winning_trades": r["winning_trades"],
                "max_drawdown_pct": r["max_drawdown_pct"],
            }
        except ValueError as err:
            entry["out_of_sample_error"] = str(err)

    return {
        "strategy": strategy_key,
        "pair": pair,
        "combinations_tested": len(combos),
        "combinations_with_result": len(in_sample_results),
        "starting_balance": starting_balance,
        "ranked_by_in_sample": in_sample_results[:20],
        "top_with_out_of_sample": top,
    }
