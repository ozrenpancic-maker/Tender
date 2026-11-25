"""Ablacijski test (ChatGPT savjet, točka 1): izmjeri DODAJE li dodatan izvor podataka (izvan
čiste cijene) ičemu, umjesto da se pretpostavi da pomaže samo zato što "zvuči korisno".

POŠTENO O OPSEGU: korisnik je tražio kripto -> +Wall Street -> +Wall Street+vijesti. Iz OVOG
razvojnog okruženja to nije izvodivo - Stooq (Wall Street) je blokiran (anti-bot filter, vidi
README), a CryptoPanic/Reddit/FRED traže osobne API ključeve koje ovo okruženje nema. Umjesto
toga, ovaj test koristi DeFiLlama TVL (Total Value Locked) kao PROXY dodatni izvor - slobodno
dostupan bez ključa, duboka povijest (~2000+ dana), ali dostupan SAMO za ETH i SOL (nema TVL
koncepta za BTC/XRP u klasičnom DeFi smislu) - zato je test ograničen na ta dva para, da usporedba
ostane poštena (ISTI primjeri u obje varijante, ne različita populacija).

Metodologija je identična onoj u app/ml/train.py (isti walk-forward, isti purge/embargo, isti
model) - jedina razlika je JEDNA dodatna značajka (tvl_roc7) u "+makro" varijanti.

Pokreni: python3 -m app.ml.ablation
"""
import json

from app import db
from app.ml.calibration import beats_baseline
from app.ml.dataset import HORIZONS, build_examples, walk_forward_folds
from app.ml.features import FEATURE_NAMES
from app.ml.macro_features import tvl_roc_feature
from app.ml.train import _fit_lgbm, run_walk_forward

ABLATION_PAIRS = ["ETH/USDT", "SOL/USDT"]  # jedini parovi s TVL serijom - usporedba ostaje poštena


def _enrich_with_tvl(conn, examples: list[dict]) -> list[dict]:
    """Dodaje 'tvl_roc7' svakom primjeru (već izgrađenom preko build_examples) i izbacuje one bez
    vrijednosti - ISTA populacija kao baseline prije ovog koraka, samo suženo na primjere gdje i
    TVL podatak postoji (iskreno: to je gotovo uvijek cijelo razdoblje jer DeFiLlama ima duboku
    povijest, ali provjera je tu da se nikad ne izmisli vrijednost)."""
    by_pair: dict[str, list[dict]] = {}
    for ex in examples:
        by_pair.setdefault(ex["pair"], []).append(ex)

    enriched = []
    for pair, pair_examples in by_pair.items():
        opened_ats = [ex["opened_at"] for ex in pair_examples]
        start_ts, end_ts = min(opened_ats), max(opened_ats)
        tvl_values = tvl_roc_feature(conn, pair, opened_ats, start_ts, end_ts)
        for ex, tvl in zip(pair_examples, tvl_values):
            if tvl is None:
                continue
            new_ex = dict(ex)
            new_ex["features"] = {**ex["features"], "tvl_roc7": tvl}
            enriched.append(new_ex)
    enriched.sort(key=lambda e: e["opened_at"])
    return enriched


def run_ablation(horizon_key: str = "24h") -> dict:
    conn = db.get_connection()
    try:
        all_examples = build_examples(conn, horizon_key)
        examples = [ex for ex in all_examples if ex["pair"] in ABLATION_PAIRS]
        print(f"Baseline primjeri (ETH+SOL, {horizon_key}): {len(examples)}")

        enriched = _enrich_with_tvl(conn, examples)
        print(f"+TVL primjeri (nakon izbacivanja onih bez TVL podatka): {len(enriched)}")

        # Presijeci baseline na ISTE primjere kao enriched (parovi po opened_at+pair) - poštena
        # usporedba znači identičnu populaciju u obje varijante, ne samo isti broj.
        enriched_keys = {(e["pair"], e["opened_at"]) for e in enriched}
        baseline_matched = [ex for ex in examples if (ex["pair"], ex["opened_at"]) in enriched_keys]

        purge_seconds = HORIZONS[horizon_key]["steps_ahead"] * HORIZONS[horizon_key]["interval_min"] * 60

        print("\n--- Baseline (samo cijena/tehnički, FEATURE_NAMES) ---")
        baseline_wf = run_walk_forward(baseline_matched, _fit_lgbm, purge_seconds)
        print(json.dumps({k: v for k, v in (baseline_wf or {}).items() if k != "reliability"}, indent=2))

        print("\n--- +TVL (ista populacija, + tvl_roc7 značajka) ---")
        extra_feature_names = FEATURE_NAMES + ["tvl_roc7"]
        enriched_wf = _run_walk_forward_custom_features(enriched, extra_feature_names, purge_seconds)
        print(json.dumps({k: v for k, v in (enriched_wf or {}).items() if k != "reliability"}, indent=2))

        if baseline_wf and enriched_wf:
            delta = enriched_wf["brier_score"] - baseline_wf["brier_score"]
            print(f"\nBrier score razlika (+TVL - baseline): {delta:+.5f} (NIŽE je bolje; {'+TVL bolji' if delta < 0 else 'baseline bolji ili isto'})")

        return {"baseline": baseline_wf, "with_tvl": enriched_wf}
    finally:
        conn.close()


def _run_walk_forward_custom_features(examples: list[dict], feature_names: list[str], purge_seconds: int) -> dict | None:
    """Isto kao app.ml.train.run_walk_forward, ali s proizvoljnim popisom značajki (ne samo
    modul-level FEATURE_NAMES) - treba za usporedbu baseline vs +TVL skup značajki."""
    import numpy as np

    from app.ml.calibration import CLASSES, evaluate
    from app.ml.train import _calibrate, _probs_in_class_order

    folds = walk_forward_folds(examples, purge_seconds=purge_seconds)
    if not folds:
        return None
    class_to_idx = {c: i for i, c in enumerate(CLASSES)}

    def to_xy(exs):
        X = np.array([[ex["features"][name] for name in feature_names] for ex in exs], dtype=float)
        y_idx = np.array([class_to_idx[ex["label"]] for ex in exs])
        return X, y_idx, [ex["label"] for ex in exs]

    all_true, all_probs, all_train_labels = [], [], []
    for train_fit, calibrate_set, test_set in folds:
        X_fit, y_fit, _ = to_xy(train_fit)
        X_calib, y_calib, calib_labels = to_xy(calibrate_set)
        X_test, _, test_labels = to_xy(test_set)

        base_model = _fit_lgbm(X_fit, y_fit)
        calibrated = _calibrate(base_model, X_calib, y_calib)
        probs = _probs_in_class_order(calibrated, X_test)

        all_true.extend(test_labels)
        all_probs.extend(probs)
        all_train_labels.extend([ex["label"] for ex in train_fit])
        all_train_labels.extend(calib_labels)

    return evaluate(all_true, all_probs, all_train_labels)


def main():
    result = run_ablation("24h")
    b, t = result["baseline"], result["with_tvl"]
    if b and t:
        print("\n=== ZAKLJUČAK ===")
        print(f"Baseline prolazi walk-forward provjeru: {beats_baseline(b)}")
        print(f"+TVL prolazi walk-forward provjeru: {beats_baseline(t)}")


if __name__ == "__main__":
    main()
