from app.strategies import dip_buy_volume, equity_filtered, multi_macro_filter, rsi_meanrev, sma_crossover

GENERIC_STRATEGIES = {
    "sma_crossover": {"label": sma_crossover.LABEL, "default_params": sma_crossover.DEFAULT_PARAMS, "decide": sma_crossover.decide, "needs_aux": []},
    "rsi_meanrev": {"label": rsi_meanrev.LABEL, "default_params": rsi_meanrev.DEFAULT_PARAMS, "decide": rsi_meanrev.decide, "needs_aux": []},
    "dip_buy_volume": {"label": dip_buy_volume.LABEL, "default_params": dip_buy_volume.DEFAULT_PARAMS, "decide": dip_buy_volume.decide, "needs_aux": []},
    "equity_filtered": {
        "label": equity_filtered.LABEL,
        "default_params": equity_filtered.DEFAULT_PARAMS,
        "decide": equity_filtered.decide,
        "needs_aux": equity_filtered.NEEDS_AUX,
    },
    "multi_macro_filter": {
        "label": multi_macro_filter.LABEL,
        "default_params": multi_macro_filter.DEFAULT_PARAMS,
        "decide": multi_macro_filter.decide,
        "needs_aux": multi_macro_filter.NEEDS_AUX,
    },
}
