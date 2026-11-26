"""Trenira LightGBM (glavni model) i logističku regresiju (kontrolni model - ako LightGBM pobjeđuje
samo za nijansu, a logistička regresija NE pokazuje nikakvu prednost, to je signal za oprez prema
overfittingu) po horizontu, s walk-forward validacijom (vidi dataset.py).

Pokreni: python3 -m app.ml.train
Zapisuje u data/models/<horizon>.json (metapodaci + walk-forward metrike) i
data/models/<horizon>_lgbm.joblib / <horizon>_logreg.joblib (spremljeni pipeline-i).
"""
import json
import time
from pathlib import Path

import joblib
import numpy as np
from lightgbm import LGBMClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app import db
from app.ml.calibration import CLASSES, beats_baseline, evaluate
from app.ml.dataset import HORIZONS, build_examples, walk_forward_folds
from app.ml.features import FEATURE_NAMES

MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "models"
CLASS_TO_IDX = {c: i for i, c in enumerate(CLASSES)}


def _to_xy(examples: list[dict]):
    X = np.array([[ex["features"][name] for name in FEATURE_NAMES] for ex in examples], dtype=float)
    y_labels = [ex["label"] for ex in examples]
    y_idx = np.array([CLASS_TO_IDX[label] for label in y_labels])
    return X, y_idx, y_labels


def _fit_lgbm(X_fit, y_idx_fit):
    model = LGBMClassifier(
        objective="multiclass",
        num_class=3,
        n_estimators=150,
        max_depth=4,
        learning_rate=0.05,
        min_child_samples=30,
        subsample=0.8,
        colsample_bytree=0.8,
        verbosity=-1,
        random_state=42,
    )
    model.fit(X_fit, y_idx_fit)
    return model


def _fit_logreg(X_fit, y_idx_fit):
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
    model.fit(X_fit, y_idx_fit)
    return model


def _calibrate(fitted_model, X_calib, y_idx_calib):
    calibrated = CalibratedClassifierCV(estimator=FrozenEstimator(fitted_model), method="isotonic")
    calibrated.fit(X_calib, y_idx_calib)
    return calibrated


def _probs_in_class_order(model, X) -> list[list[float]]:
    """model.classes_ je podskup/permutacija [0,1,2] - poravna stupce na CLASSES redoslijed."""
    raw = model.predict_proba(X)
    classes = list(model.classes_)
    out = []
    for row in raw:
        full = [0.0, 0.0, 0.0]
        for idx, cls in enumerate(classes):
            full[cls] = row[idx]
        out.append(full)
    return out


def run_walk_forward(examples: list[dict], fit_fn, purge_seconds: int = 0) -> dict | None:
    folds = walk_forward_folds(examples, purge_seconds=purge_seconds)
    if not folds:
        return None
    all_true: list[str] = []
    all_probs: list[list[float]] = []
    all_train_labels: list[str] = []
    for train_fit, calibrate_set, test_set in folds:
        X_fit, y_fit, _ = _to_xy(train_fit)
        X_calib, y_calib, calib_labels = _to_xy(calibrate_set)
        X_test, _, test_labels = _to_xy(test_set)

        base_model = fit_fn(X_fit, y_fit)
        calibrated = _calibrate(base_model, X_calib, y_calib)
        probs = _probs_in_class_order(calibrated, X_test)

        all_true.extend(test_labels)
        all_probs.extend(probs)
        all_train_labels.extend([ex["label"] for ex in train_fit])
        all_train_labels.extend(calib_labels)

    return evaluate(all_true, all_probs, all_train_labels)


def train_horizon(conn, horizon_key: str, models_dir: Path = MODELS_DIR) -> dict:
    spec = HORIZONS[horizon_key]
    examples = build_examples(conn, horizon_key)
    result: dict = {
        "horizon": horizon_key,
        "horizon_label": spec["label"],
        "n_examples": len(examples),
        "trained_at": int(time.time()),
        "feature_names": FEATURE_NAMES,
        "classes": CLASSES,
    }

    purge_seconds = spec["steps_ahead"] * spec["interval_min"] * 60
    lgbm_wf = run_walk_forward(examples, _fit_lgbm, purge_seconds)
    logreg_wf = run_walk_forward(examples, _fit_logreg, purge_seconds)
    result["lightgbm_walk_forward"] = lgbm_wf
    result["logreg_walk_forward"] = logreg_wf

    if lgbm_wf is None:
        result["validated"] = False
        result["reason"] = f"Nedovoljno primjera za walk-forward validaciju (n={len(examples)})."
        return result

    result["validated"] = bool(beats_baseline(lgbm_wf))
    if not result["validated"]:
        result["reason"] = (
            f"LightGBM Brier score ({lgbm_wf['brier_score']}) nije bolji od naivne bazne linije "
            f"({lgbm_wf['baseline_brier_score']}) na walk-forward testu - model NE pokazuje stvarnu "
            f"prednost na ovom horizontu s dostupnim podacima. Live signal za ovaj horizont vraća WAIT."
        )

    # Produkcijski model: treniran na SVIM podacima (zadnjih 20% kronološki kao kalibracija),
    # koristi se za uživo predikciju - ali njegova "poštenost" dolazi iz walk-forward metrika iznad,
    # ne iz performansa na vlastitom treningu.
    split = int(len(examples) * 0.8)
    train_fit, calib = examples[:split], examples[split:]
    X_fit, y_fit, _ = _to_xy(train_fit)
    X_calib, y_calib, _ = _to_xy(calib)
    production_model = _calibrate(_fit_lgbm(X_fit, y_fit), X_calib, y_calib)

    models_dir.mkdir(parents=True, exist_ok=True)
    model_path = models_dir / f"{horizon_key}_lgbm.joblib"
    joblib.dump(production_model, model_path)
    result["model_path"] = str(model_path.name)
    return result


def main():
    conn = db.get_connection()
    try:
        all_results = {}
        for horizon_key in HORIZONS:
            print(f"--- Treniram horizont: {horizon_key} ---")
            res = train_horizon(conn, horizon_key)
            all_results[horizon_key] = res
            print(json.dumps({k: v for k, v in res.items() if k not in ("lightgbm_walk_forward",)}, indent=2, ensure_ascii=False))
            if res.get("lightgbm_walk_forward"):
                print("walk-forward:", json.dumps({k: v for k, v in res["lightgbm_walk_forward"].items() if k != "reliability"}, indent=2))
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        with open(MODELS_DIR / "metadata.json", "w") as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
