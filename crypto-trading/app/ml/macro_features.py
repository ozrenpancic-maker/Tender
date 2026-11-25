"""Opcionalne makro/on-chain značajke za ML ablacijski test (ChatGPT savjet, točka 1 - izmjeri
koliko izvori izvan čiste cijene stvarno pomažu, prije nego im se vjeruje). Point-in-time ispravno
jer se oslanja na app.macro_store.load_series, koja već filtrira po available_date (dan kad je
podatak STVARNO bio dostupan), ne observed_date - vidi macro_store.py za potpuno objašnjenje.

Vidi README "Ablacijski test" za zašto je OVO (DeFiLlama TVL) korišteno kao PROXY umjesto
doslovno Wall Street/vijesti - Stooq je blokiran iz razvojnog okruženja, a CryptoPanic/Reddit/FRED
traže osobne API ključeve koje ovo okruženje nema. DeFiLlama TVL je izvor koji JEST dostupan i ima
duboku (~2000+ dana) besplatnu povijest bez ključa, pa je korišten za stvarno testiranu
demonstraciju metodologije."""
import bisect

from app.macro_store import load_series

TVL_SERIES_BY_PAIR = {"ETH/USDT": "ETHEREUM_TVL", "SOL/USDT": "SOLANA_TVL"}


def tvl_roc_feature(conn, pair: str, opened_ats: list[int], start_ts: int, end_ts: int, lookback_points: int = 7) -> list[float | None]:
    """Vraća postotnu promjenu TVL-a (lookback_points dana unatrag) za svaki opened_at - None ako
    par nema TVL seriju (npr. BTC/XRP) ili nema dovoljno povijesti na taj datum."""
    series_id = TVL_SERIES_BY_PAIR.get(pair)
    if series_id is None:
        return [None] * len(opened_ats)

    points = load_series(conn, "defillama", series_id, start_ts - lookback_points * 2 * 86400, end_ts)
    if not points:
        return [None] * len(opened_ats)
    ts_sorted = [p[0] for p in points]
    val_sorted = [p[1] for p in points]

    out = []
    for ts in opened_ats:
        idx = bisect.bisect_right(ts_sorted, ts) - 1
        if idx < lookback_points:
            out.append(None)
            continue
        now_v, prev_v = val_sorted[idx], val_sorted[idx - lookback_points]
        out.append(100 * (now_v - prev_v) / prev_v if prev_v else None)
    return out
