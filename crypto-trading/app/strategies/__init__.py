from app.strategies import dip_buy_volume, rsi_meanrev, sma_crossover

GENERIC_STRATEGIES = {
    "sma_crossover": {"label": sma_crossover.LABEL, "default_params": sma_crossover.DEFAULT_PARAMS, "decide": sma_crossover.decide},
    "rsi_meanrev": {"label": rsi_meanrev.LABEL, "default_params": rsi_meanrev.DEFAULT_PARAMS, "decide": rsi_meanrev.decide},
    "dip_buy_volume": {"label": dip_buy_volume.LABEL, "default_params": dip_buy_volume.DEFAULT_PARAMS, "decide": dip_buy_volume.decide},
}
