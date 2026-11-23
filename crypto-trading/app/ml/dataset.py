"""Gradi skup podataka (značajke + labele) po horizontu, POOLED preko BTC/ETH/SOL (više podataka,
jedan opći model po horizontu - ne po paru; vidi README zašto). Parovi se namjerno NE kodiraju kao
značajka - model uči samo tehničke uzorke, ne "ovo je baš BTC", što je pretpostavka vrijedna
provjere, ali razumna polazna točka s ograničenom poviješću koju imamo za SOL.

Svaki primjer čuva i (pair, opened_at) da se walk-forward foldovi mogu posložiti STROGO kronološki
preko cijelog pooled skupa - sprječava curenje gdje bi "buduća" svijeća jednog para završila u
treningu dok je "sadašnja" svijeća drugog para u testu.
"""
from app.candles import load_candles, resample_candles
from app.ml.features import FEATURE_NAMES, compute_feature_frame
from app.ml.labels import label_series

PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]

# horizon -> (interval_min na kojem računamo značajke/label, source_interval_min ako treba resample, steps_ahead)
HORIZONS = {
    "1h": {"label": "1 sat", "interval_min": 60, "source_interval_min": 5, "steps_ahead": 1},
    "4h": {"label": "4 sata", "interval_min": 240, "source_interval_min": 5, "steps_ahead": 1},
    "24h": {"label": "24 sata", "interval_min": 1440, "source_interval_min": 1440, "steps_ahead": 1},
    "7d": {"label": "7 dana", "interval_min": 1440, "source_interval_min": 1440, "steps_ahead": 7},
}

MIN_WARMUP = 200  # svijeća potrebnih prije prve značajke (EMA200 je najdulja) - redovi prije se izbacuju


def _load_base_candles(conn, pair: str, horizon_key: str) -> list:
    spec = HORIZONS[horizon_key]
    if spec["interval_min"] == spec["source_interval_min"]:
        return load_candles(conn, "binance", pair, spec["interval_min"], 0, 2_000_000_000)
    source = load_candles(conn, "binance", pair, spec["source_interval_min"], 0, 2_000_000_000)
    return resample_candles(source, spec["source_interval_min"], spec["interval_min"])


def build_examples(conn, horizon_key: str) -> list[dict]:
    """Vraća listu {features: {...}, label: str, pair: str, opened_at: int}, SORTIRANO kronološki
    preko svih parova zajedno. Redovi s nedovoljno povijesti ili bez labele (zadnjih steps_ahead
    svijeća) su izbačeni."""
    spec = HORIZONS[horizon_key]
    examples = []
    for pair in PAIRS:
        candles = _load_base_candles(conn, pair, horizon_key)
        if len(candles) < MIN_WARMUP + spec["steps_ahead"] + 50:
            continue
        feature_rows = compute_feature_frame(candles)
        atr_norm = [row["atr14_norm"] for row in feature_rows]
        labels = label_series(candles, spec["steps_ahead"], atr_norm)
        for i in range(MIN_WARMUP, len(candles) - spec["steps_ahead"]):
            row = feature_rows[i]
            if labels[i] is None or any(row[name] is None for name in FEATURE_NAMES):
                continue
            examples.append(
                {
                    "features": {name: row[name] for name in FEATURE_NAMES},
                    "label": labels[i],
                    "pair": pair,
                    "opened_at": candles[i].opened_at,
                }
            )
    examples.sort(key=lambda e: e["opened_at"])
    return examples


def walk_forward_folds(examples: list[dict], n_folds: int = 5, min_train: int = 300):
    """Generira (train_fit, calibrate, test) triple-ove, kronološki, expanding-window:
    - podijeli `examples` (već sortirano po vremenu) u `n_folds` jednakih kronoloških blokova,
    - za svaki fold k=1..n_folds-1: train = blokovi[0..k-1] (zadnjih 20% toga je `calibrate`,
      ostatak je `train_fit`), test = blok k (NIKAD korišten za fit/kalibraciju).
    Smanjuje n_folds ako nema dovoljno podataka za `min_train` primjera u prvom treningu."""
    n = len(examples)
    if n < min_train * 2:
        return []
    while n_folds > 2 and n // n_folds < min_train:
        n_folds -= 1
    block_size = n // n_folds
    blocks = [examples[i * block_size : (i + 1) * block_size] for i in range(n_folds - 1)]
    blocks.append(examples[(n_folds - 1) * block_size :])  # zadnji blok pokupi ostatak

    folds = []
    for k in range(1, n_folds):
        train_all = [e for block in blocks[:k] for e in block]
        if len(train_all) < min_train:
            continue
        split = int(len(train_all) * 0.8)
        train_fit, calibrate = train_all[:split], train_all[split:]
        if len(calibrate) < 20:
            continue
        folds.append((train_fit, calibrate, blocks[k]))
    return folds
