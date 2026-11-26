"""Sigurno, automatizirano periodično ponovno treniranje AI Prediction Engine-a - korisnik je
tražio "AI učenje" iz novih podataka. Pravo "uči u stvarnom vremenu" (online learning) je
odbačeno kao previše rizično (model bi se mogao tiho pogoršati bez provjere) - umjesto toga, ovo
je PERIODIČNO ponovno treniranje s "promotion gate": novi model zamjenjuje stari SAMO ako na
walk-forward testu nije gori od trenutnog uživo modela. Ako je gori (ili izgubi validaciju koju je
prije imao), stari model ostaje na snazi i to se jasno zapisuje - NIKAD tiho pogoršanje.

Pokreni ručno: python3 -m app.ml.retrain_scheduled
Za tjedno automatsko pokretanje vidi README "Automatsko ponovno treniranje" (Windows Task Scheduler).

Koraci:
1. Osvježi povijesne svijeće za sve ML parove/intervale (app/binance_history_client) - bez ovoga
   bi se "ponovno treniralo" na istim starim podacima, ništa ne bi naučilo.
2. Treniraj svaki horizont u STAGING direktorij (ne dira uživo model dok se ne odluči promocija).
3. Usporedi novi (kandidat) walk-forward Brier score s trenutnim uživo modelom po horizontu.
4. Promoviraj (zamijeni uživo model+metapodatke) SAMO ako kandidat nije gori - inače zadrži staro.
5. Zapiši JEDAN redak u data/models/retrain_log.jsonl (append) - vidljiva povijest svake odluke.
"""
import json
import shutil
import time
from pathlib import Path

from app import binance_history_client, db
from app.ml.dataset import HORIZONS, PAIRS
from app.ml.train import MODELS_DIR, train_horizon

STAGING_DIR = MODELS_DIR / "_staging"
RETRAIN_LOG_PATH = MODELS_DIR / "retrain_log.jsonl"

# horizon_key -> Binance 'interval' string koji app/binance_history_client.sync_to_db očekuje
SYNC_INTERVAL_FOR_HORIZON = {"1h": "1h", "4h": "4h", "24h": "1d", "7d": "1d"}


def _refresh_candles(conn) -> list[str]:
    """Osvježi zadnjih ~400 dana povijesti za sve ML parove/intervale - dovoljno za ponovno
    treniranje bez ponovnog preuzimanja cijele povijesti svaki put. ON CONFLICT DO UPDATE u
    sync_to_db čini ovo sigurnim za ponavljanje (ne duplicira retke)."""
    since = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 400 * 86400))
    errors = []
    seen_intervals = set(SYNC_INTERVAL_FOR_HORIZON.values())
    for pair in PAIRS:
        for interval in seen_intervals:
            try:
                n = binance_history_client.sync_to_db(conn, pair, since=since, interval=interval)
                print(f"  sinkronizirano {pair} {interval}: {n} svijeća")
            except Exception as err:
                msg = f"{pair} {interval}: {err}"
                print(f"  GREŠKA pri sinkronizaciji {msg}")
                errors.append(msg)
    return errors


def _should_promote(candidate: dict, previous: dict | None) -> tuple[bool, str]:
    """Vraća (promoviraj_li, razlog) - NIKAD ne promovira kandidat koji je gori od trenutnog
    uživo modela po walk-forward Brier scoreu (niže je bolje)."""
    cand_wf = candidate.get("lightgbm_walk_forward")
    if cand_wf is None:
        return False, f"Kandidat nema dovoljno primjera za walk-forward (n={candidate['n_examples']}) - zadržan stari model."

    if previous is None:
        return True, "Nema prijašnjeg modela za usporedbu - prvi trening, promoviran."

    prev_wf = previous.get("lightgbm_walk_forward")
    prev_validated = bool(previous.get("validated"))
    cand_validated = bool(candidate.get("validated"))

    if not prev_validated:
        if cand_validated:
            return True, "Prijašnji model NIJE bio validiran, novi JEST - promoviran."
        return True, "Ni prijašnji ni novi model nisu validirani (oba vraćaju WAIT uživo) - promoviran radi svježih metapodataka, ponašanje se ne mijenja."

    # prijašnji JEST bio validiran - novi mora biti barem jednako dobar, inače se NE promovira
    if not cand_validated:
        return False, f"Prijašnji model je bio validiran, novi NIJE (Brier {cand_wf['brier_score'] if cand_wf else 'N/A'}) - zadržan stari model, bez regresije."

    prev_brier = prev_wf["brier_score"] if prev_wf else None
    cand_brier = cand_wf["brier_score"]
    if prev_brier is None or cand_brier <= prev_brier:
        return True, f"Oba validirana, novi Brier ({cand_brier}) <= stari ({prev_brier}) - promoviran."
    return False, f"Oba validirana, ali novi Brier ({cand_brier}) GORI od starog ({prev_brier}) - zadržan stari model, bez regresije."


def run() -> dict:
    if STAGING_DIR.exists():
        shutil.rmtree(STAGING_DIR)
    STAGING_DIR.mkdir(parents=True)

    conn = db.get_connection()
    try:
        print("Korak 1/3: osvježavam povijesne svijeće...")
        sync_errors = _refresh_candles(conn)

        print("Korak 2/3: treniram kandidate (staging, uživo model još netaknut)...")
        old_metadata = {}
        metadata_path = MODELS_DIR / "metadata.json"
        if metadata_path.exists():
            old_metadata = json.loads(metadata_path.read_text())

        decisions = {}
        new_metadata = dict(old_metadata)
        for horizon_key in HORIZONS:
            print(f"  --- {horizon_key} ---")
            candidate = train_horizon(conn, horizon_key, models_dir=STAGING_DIR)
            previous = old_metadata.get(horizon_key)
            promote, reason = _should_promote(candidate, previous)
            decisions[horizon_key] = {
                "promoted": promote,
                "reason": reason,
                "candidate_validated": candidate.get("validated"),
                "candidate_brier": (candidate.get("lightgbm_walk_forward") or {}).get("brier_score"),
                "previous_validated": (previous or {}).get("validated"),
                "previous_brier": ((previous or {}).get("lightgbm_walk_forward") or {}).get("brier_score"),
            }
            print(f"    {'PROMOVIRAN' if promote else 'ZADRŽAN STARI'}: {reason}")
            if promote:
                staged_model = STAGING_DIR / f"{horizon_key}_lgbm.joblib"
                if staged_model.exists():
                    shutil.copy2(staged_model, MODELS_DIR / f"{horizon_key}_lgbm.joblib")
                new_metadata[horizon_key] = candidate

        print("Korak 3/3: zapisujem metapodatke i log...")
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(new_metadata, indent=2, ensure_ascii=False))

        log_entry = {
            "at": int(time.time()),
            "at_human": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "sync_errors": sync_errors,
            "decisions": decisions,
        }
        with open(RETRAIN_LOG_PATH, "a") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        return log_entry
    finally:
        shutil.rmtree(STAGING_DIR, ignore_errors=True)
        conn.close()


def read_log(limit: int = 20) -> list[dict]:
    if not RETRAIN_LOG_PATH.exists():
        return []
    lines = RETRAIN_LOG_PATH.read_text().strip().splitlines()
    return [json.loads(line) for line in lines[-limit:]][::-1]


if __name__ == "__main__":
    result = run()
    print("\n=== GOTOVO ===")
    print(json.dumps(result, indent=2, ensure_ascii=False))
