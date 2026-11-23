"""Uživo AI Prediction Engine - učitava modele trenirane u train.py i daje predikciju za trenutnu
(zadnju dostupnu) svijeću po paru/horizontu.

POŠTENO STANJE (vidi README "AI Prediction Engine" za detalje): na prvom treniranju nad stvarnim
podacima dostupnim u ovom razvojnom okruženju (BTC/ETH/SOL, ograničena povijest za 1h/4h), NIJEDAN
od 4 horizonta nije prošao validaciju (LightGBM nije značajno bolji od naivne bazne linije na
walk-forward testu - vidi data/models/metadata.json). To znači da `compute_prediction` za SVE
horizonte trenutno vraća WAIT / "NEMA DOVOLJNO POUZDANIH PODATAKA" - to NIJE bug, to je pravilo #8
i #12/#13 iz specifikacije na djelu: nevalidiran model se ne prikazuje kao da radi. Kad se jednom
ponovno trenira (više povijesti, dodatne značajke iz postojećih makro/derivatives/sentiment
klijenata), ovaj gate automatski počinje davati prave predikcije bez promjene ovog koda.
"""
import json
import time
from pathlib import Path

import joblib

from app import binance_history_client
from app.ml.calibration import CLASSES
from app.ml.dataset import HORIZONS
from app.ml.features import FEATURE_NAMES, compute_feature_frame

MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "models"

AI_SCORE_BANDS = [
    (0, 25, "STRONG SELL"),
    (26, 45, "SELL"),
    (46, 55, "WAIT"),
    (56, 75, "BUY"),
    (76, 100, "STRONG BUY"),
]

_metadata_cache: dict | None = None
_model_cache: dict[str, object] = {}


class PredictionError(Exception):
    pass


def _load_metadata() -> dict:
    global _metadata_cache
    if _metadata_cache is None:
        path = MODELS_DIR / "metadata.json"
        if not path.exists():
            raise PredictionError("Modeli nisu trenirani - pokreni 'python3 -m app.ml.train'.")
        _metadata_cache = json.loads(path.read_text())
    return _metadata_cache


def _load_model(horizon: str):
    if horizon not in _model_cache:
        path = MODELS_DIR / f"{horizon}_lgbm.joblib"
        if not path.exists():
            raise PredictionError(f"Nema spremljenog modela za horizont '{horizon}'.")
        _model_cache[horizon] = joblib.load(path)
    return _model_cache[horizon]


def _ai_score(probs: dict[str, float]) -> int:
    """AI Score = ocjena KVALITETE I SMJERA signala, NE izravna vjerojatnost rasta (pravilo #7).
    Formula: linearna skala gdje P(up)=1 -> 100, P(sideways)=1 -> 50, P(down)=1 -> 0. Transparentna,
    provjerljiva iz probs-a, ne proizvoljno ponderirana 'crna kutija'."""
    score = 100 * probs["up"] + 50 * probs["sideways"] + 0 * probs["down"]
    return round(max(0, min(100, score)))


def _category(score: int) -> str:
    for lo, hi, label in AI_SCORE_BANDS:
        if lo <= score <= hi:
            return label
    return "WAIT"


def _reasons(features: dict) -> tuple[list[str], list[str]]:
    """Jednostavna, provjerljiva (ne SHAP) interpretacija ključnih značajki u razloge na
    hrvatskom - svaki razlog je izravno izveden iz vrijednosti značajke s dokumentiranim pragom."""
    positives, negatives = [], []
    if features["rsi14"] is not None:
        if features["rsi14"] < 30:
            positives.append(f"RSI14 u prodanosti ({features['rsi14']:.0f}) - prostor za odboj.")
        elif features["rsi14"] > 70:
            negatives.append(f"RSI14 u prekupljenosti ({features['rsi14']:.0f}) - rizik korekcije.")
    if features["macd_hist_norm"] is not None:
        if features["macd_hist_norm"] > 0:
            positives.append("MACD histogram pozitivan - momentum rasta.")
        else:
            negatives.append("MACD histogram negativan - momentum pada.")
    if features["ema50_dist"] is not None:
        if features["ema50_dist"] > 0:
            positives.append("Cijena iznad EMA50 - kratkoročni trend gore.")
        else:
            negatives.append("Cijena ispod EMA50 - kratkoročni trend dolje.")
    if features["ema200_dist"] is not None:
        if features["ema200_dist"] > 0:
            positives.append("Cijena iznad EMA200 - dugoročni trend gore.")
        else:
            negatives.append("Cijena ispod EMA200 - dugoročni trend dolje (bear regime).")
    if features["bb_pct_b"] is not None:
        if features["bb_pct_b"] > 0.95:
            negatives.append("Cijena na/iznad gornje Bollinger vrpce - istegnuto, rizik povratka.")
        elif features["bb_pct_b"] < 0.05:
            positives.append("Cijena na/ispod donje Bollinger vrpce - istegnuto na dolje.")
    if features["volume_rel20"] is not None and features["volume_rel20"] > 0.5:
        positives.append("Volumen znatno iznad 20-prosjeka - pokret ima potvrdu.")
    return positives[:5], negatives[:5]


def _data_quality(candles: list, horizon: str) -> dict:
    spec = HORIZONS[horizon]
    if not candles:
        return {"ok": False, "note": "Nema svijeća."}
    age_seconds = time.time() - (candles[-1].opened_at + spec["interval_min"] * 60)
    stale = age_seconds > spec["interval_min"] * 60 * 2
    return {
        "ok": not stale,
        "candles_used": len(candles),
        "latest_candle_age_minutes": round(age_seconds / 60, 1),
        "note": "Zadnja svijeća je neobično stara - podaci možda nisu svježi." if stale else "U redu.",
    }


def compute_prediction(pair: str, horizon: str) -> dict:
    if horizon not in HORIZONS:
        raise PredictionError(f"Nepoznat horizont '{horizon}'. Dostupno: {list(HORIZONS)}")
    spec = HORIZONS[horizon]
    metadata = _load_metadata()
    info = metadata.get(horizon, {})

    base = {
        "pair": pair,
        "horizon": horizon,
        "horizon_label": spec["label"],
        "model_version": info.get("trained_at"),
        "generated_at": int(time.time()),
    }

    if not info.get("validated"):
        return {
            **base,
            "decision": "NEMA DOVOLJNO POUZDANIH PODATAKA",
            "ai_score": None,
            "p_up": None,
            "p_down": None,
            "p_sideways": None,
            "reasons_for": [],
            "reasons_against": [
                info.get("reason", "Model za ovaj horizont nije prošao walk-forward validaciju.")
            ],
            "historical_validation": info.get("lightgbm_walk_forward"),
            "data_quality": {"ok": False, "note": "Model nije validiran - vidi reasons_against."},
        }

    # Treba barem ~210 svijeća (EMA200 zagrijavanje) NA OVOM INTERVALU - "dana" ovisi o intervalu,
    # ne o horizontu. Prijašnja formula (interval_min // 60) je za 4h/24h/7d davala premalo dana
    # (npr. 30 dana na 1d intervalu = samo 30 svijeća) i trajno blokirala te horizonte čak i nakon
    # uspješne validacije - otkriveno u ChatGPT-ovoj neovisnoj reviziji.
    min_candles = 230
    days_needed = max(30, -(-(min_candles * spec["interval_min"]) // 1440) + 10)  # ceil + 10 dana zaliha
    try:
        candles = binance_history_client.fetch_recent(pair, days=days_needed, interval=_binance_interval(horizon))
    except Exception as err:
        return {**base, "decision": "NEMA DOVOLJNO POUZDANIH PODATAKA", "ai_score": None, "error": str(err)}

    if len(candles) < 210:
        return {
            **base,
            "decision": "NEMA DOVOLJNO POUZDANIH PODATAKA",
            "ai_score": None,
            "reasons_against": [f"Samo {len(candles)} svijeća dostupno, treba barem 210 (EMA200 zagrijavanje)."],
        }

    feature_rows = compute_feature_frame(candles)
    last = feature_rows[-1]
    if any(last[name] is None for name in FEATURE_NAMES):
        return {**base, "decision": "NEMA DOVOLJNO POUZDANIH PODATAKA", "ai_score": None, "reasons_against": ["Nedostaju neke značajke na zadnjoj svijeći."]}

    # ChatGPT-ova neovisna revizija: kvaliteta podataka se računala i vraćala, ali NIJE blokirala
    # BUY/SELL kad je zadnja svijeća zastarjela - popravljeno, zastarjeli podaci sada prisilno
    # vraćaju WAIT umjesto moguće krive preporuke na staroj cijeni.
    quality = _data_quality(candles, horizon)
    if not quality["ok"]:
        return {
            **base,
            "decision": "NEMA DOVOLJNO POUZDANIH PODATAKA",
            "ai_score": None,
            "reasons_against": [f"Podaci zastarjeli: {quality['note']}"],
            "data_quality": quality,
        }

    model = _load_model(horizon)
    X = [[last[name] for name in FEATURE_NAMES]]
    raw_probs = model.predict_proba(X)[0]
    classes = list(model.classes_)
    probs = {CLASSES[cls]: float(p) for cls, p in zip(classes, raw_probs)}
    for c in CLASSES:
        probs.setdefault(c, 0.0)
    total = sum(probs.values()) or 1.0
    probs = {c: v / total for c, v in probs.items()}  # osiguraj da zbroj bude točno 100%

    score = _ai_score(probs)
    category = _category(score)
    positives, negatives = _reasons(last)

    return {
        **base,
        "decision": category,
        "ai_score": score,
        "p_up": round(probs["up"], 4),
        "p_down": round(probs["down"], 4),
        "p_sideways": round(probs["sideways"], 4),
        "reasons_for": positives,
        "reasons_against": negatives,
        "historical_validation": info.get("lightgbm_walk_forward"),
        "data_quality": _data_quality(candles, horizon),
        "price": candles[-1].close,
        "as_of": candles[-1].opened_at,
    }


def _binance_interval(horizon: str) -> str:
    return {"1h": "1h", "4h": "4h", "24h": "1d", "7d": "1d"}[horizon]


def compute_all(pairs: list[str]) -> dict:
    result = {}
    for pair in pairs:
        result[pair] = {}
        for horizon in HORIZONS:
            try:
                result[pair][horizon] = compute_prediction(pair, horizon)
            except Exception as err:
                result[pair][horizon] = {"error": str(err)}
    return result
