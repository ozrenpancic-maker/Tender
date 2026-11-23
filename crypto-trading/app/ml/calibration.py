"""Metrike kalibracije i poštena usporedba s naivnom baznom linijom (pravilo #7 iz specifikacije:
heuristička ocjena se ne prikazuje kao kalibrirana vjerojatnost dok se ne provjeri).

CLASSES mora biti fiksni, dogovoreni redoslijed (up, down, sideways) - koristi ga i train.py i
engine.py da se stupci vjerojatnosti ne pomiješaju.
"""
import math

CLASSES = ["up", "down", "sideways"]


def _one_hot(label: str) -> list[float]:
    return [1.0 if label == c else 0.0 for c in CLASSES]


def multiclass_brier_score(y_true: list[str], probs: list[list[float]]) -> float:
    """Prosjek sum_c (p_c - y_c)^2 preko svih primjera. 0 = savršeno, veće = lošije.
    (Naivna bazna linija koja uvijek predviđa prior ima Brier = 2*(1 - sum(prior_c^2)) / broj_klasa
    po jednoj od uobičajenih konvencija - uspoređujemo direktno s stvarno izračunatom baznom
    linijom u evaluate_against_baseline, ne s teorijskom formulom.)"""
    total = 0.0
    for y, p in zip(y_true, probs):
        target = _one_hot(y)
        total += sum((pc - tc) ** 2 for pc, tc in zip(p, target))
    return total / len(y_true) if y_true else float("nan")


def multiclass_log_loss(y_true: list[str], probs: list[list[float]], eps: float = 1e-12) -> float:
    total = 0.0
    for y, p in zip(y_true, probs):
        idx = CLASSES.index(y)
        total += -math.log(max(p[idx], eps))
    return total / len(y_true) if y_true else float("nan")


def accuracy(y_true: list[str], probs: list[list[float]]) -> float:
    correct = 0
    for y, p in zip(y_true, probs):
        pred = CLASSES[p.index(max(p))]
        if pred == y:
            correct += 1
    return correct / len(y_true) if y_true else float("nan")


def reliability_bins(y_true: list[str], probs: list[list[float]], n_bins: int = 10) -> list[dict]:
    """Standardna 'confidence vs accuracy' kalibracijska dijagrama: za svaki primjer uzmi
    max(p) (pouzdanost u predviđenu klasu) i je li predikcija bila točna, pa prosjek po binovima."""
    bins = [{"lo": i / n_bins, "hi": (i + 1) / n_bins, "n": 0, "sum_conf": 0.0, "sum_correct": 0} for i in range(n_bins)]
    for y, p in zip(y_true, probs):
        conf = max(p)
        pred = CLASSES[p.index(conf)]
        bin_idx = min(int(conf * n_bins), n_bins - 1)
        b = bins[bin_idx]
        b["n"] += 1
        b["sum_conf"] += conf
        b["sum_correct"] += int(pred == y)
    out = []
    for b in bins:
        if b["n"] == 0:
            continue
        out.append(
            {
                "range": [round(b["lo"], 2), round(b["hi"], 2)],
                "n": b["n"],
                "avg_confidence": round(b["sum_conf"] / b["n"], 4),
                "empirical_accuracy": round(b["sum_correct"] / b["n"], 4),
            }
        )
    return out


def naive_baseline_probs(train_labels: list[str], n: int) -> list[list[float]]:
    """Bazna linija 'bez vještine': uvijek predviđa udio klasa u treningu (prior), isti za sve."""
    prior = [train_labels.count(c) / len(train_labels) for c in CLASSES]
    return [list(prior) for _ in range(n)]


def evaluate(y_true: list[str], probs: list[list[float]], train_labels_for_baseline: list[str]) -> dict:
    baseline_probs = naive_baseline_probs(train_labels_for_baseline, len(y_true))
    return {
        "n": len(y_true),
        "brier_score": round(multiclass_brier_score(y_true, probs), 5),
        "baseline_brier_score": round(multiclass_brier_score(y_true, baseline_probs), 5),
        "log_loss": round(multiclass_log_loss(y_true, probs), 5),
        "baseline_log_loss": round(multiclass_log_loss(y_true, baseline_probs), 5),
        "accuracy": round(accuracy(y_true, probs), 4),
        "baseline_accuracy": round(accuracy(y_true, baseline_probs), 4),
        "reliability": reliability_bins(y_true, probs),
    }


def beats_baseline(metrics: dict, min_relative_improvement: float = 0.02) -> bool:
    """Model mora biti ZNAČAJNO bolji (niži Brier) od naivne bazne linije da se smatra validiranim -
    pravilo #12/#13: nevalidiran model ne smije aktivirati live preporuku. Koristi relativni prag
    (ne apsolutnu nulu) jer bi inače poboljšanje unutar šuma (npr. 0,0005 na Brier skali) lažno
    prošlo kao 'model radi' - to se dogodilo kod horizonta s jako neravnomjernom raspodjelom klasa
    (vidi README) prije nego je ovaj prag dodan."""
    baseline = metrics["baseline_brier_score"]
    required = baseline * min_relative_improvement
    return metrics["brier_score"] < baseline - required
