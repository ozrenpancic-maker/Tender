"""Automatizirani integritetski testovi - NE testiraju profitabilnost (za to je backtest/optimizer),
nego da sam SUSTAV ne vara sebe. Izravno inspirirano ChatGPT-ovim `checks_51.py` iz paralelnog
KriptoMVP 5.1 istraživanja (vidi README "Nezavisna provjera s ChatGPT-ovim paralelnim
istraživanjem") - ista ideja, prevedena za ovaj projekt.

Pokreni: python3 -m app.checks
"""
from dataclasses import replace

from app import db
from app.candles import Candle, load_candles
from app.costs import FEE, SLIPPAGE, buy_fill_price, sell_fill_price
from app.strategies import GENERIC_STRATEGIES
from app.strategies.base import StrategyContext

CUTOFF_INDEX = 400


def _mutate_future(candles: list[Candle], from_index: int) -> list[Candle]:
    """Vraća novi niz svijeća gdje je SVE od `from_index` nadalje dramatično promijenjeno
    (3x cijena, 5x volumen). Ako bilo koja odluka na indeksu < from_index ovisi o tome, postoji
    look-ahead bug - strategija "vidi" budućnost koju u stvarnom trgovanju ne bi imala."""
    out = list(candles[:from_index])
    for c in candles[from_index:]:
        out.append(replace(c, open=c.open * 3, high=c.high * 3, low=c.low * 3, close=c.close * 3, volume=c.volume * 5))
    return out


def _dummy_aux(candles: list[Candle]) -> list[Candle]:
    """Placeholder pomoćna serija (npr. SPX) - konstantna, identična u oba pokretanja. Svrha ovog
    testa je look-ahead u GLAVNOJ cjenovnoj seriji, ne u pomoćnim podacima, pa su ovi samo da
    strategije kojima su potrebni ne bace grešku 'podaci nedostaju'."""
    return [replace(c, open=100.0, high=100.0, low=100.0, close=100.0, volume=1.0) for c in candles]


def _dummy_series(candles: list[Candle]) -> list[tuple[int, float]]:
    return [(c.opened_at, 1.0) for c in candles]


def check_no_lookahead(candles: list[Candle]) -> None:
    """Za SVAKU registriranu strategiju: odluke na indeksima < CUTOFF_INDEX moraju biti identične
    bez obzira mijenja li se nešto od CUTOFF_INDEX nadalje. `in_position` je namjerno uvijek False
    (testira se ulazna logika - izlazna koristi iste, već provjerene indikatorske funkcije)."""
    mutated = _mutate_future(candles, CUTOFF_INDEX)

    for key, strategy in GENERIC_STRATEGIES.items():
        decide = strategy["decide"]
        params = strategy["default_params"]
        aux = {label: _dummy_aux(candles) for label in strategy.get("needs_aux", [])}
        series = {spec["series_id"]: _dummy_series(candles) for spec in strategy.get("needs_series", [])}

        for i in range(CUTOFF_INDEX):
            ctx_a = StrategyContext(candles=candles, index=i, in_position=False, params=dict(params), aux=aux, series=series)
            ctx_b = StrategyContext(candles=mutated, index=i, in_position=False, params=dict(params), aux=aux, series=series)
            decision_a, decision_b = decide(ctx_a), decide(ctx_b)
            assert decision_a == decision_b, (
                f"LOOK-AHEAD BUG u '{key}': odluka na indeksu {i} je '{decision_a}' sa stvarnom "
                f"budućnošću, ali '{decision_b}' kad je budućnost (indeks {CUTOFF_INDEX}+) promijenjena - "
                f"strategija koristi podatke koje ne bi imala u stvarnom trenutku odluke."
            )
    print(f"PASS check_no_lookahead: {len(GENERIC_STRATEGIES)} strategija, {CUTOFF_INDEX} indeksa svaka.")


def check_fee_arithmetic() -> None:
    """Konstantna cijena, jedna kupnja i jedna prodaja: naknade+slippage mogu SAMO smanjiti kapital,
    nikad ga povećati ili ostaviti netaknutim."""
    price = 100.0
    start_cash = 100.0
    qty = start_cash / buy_fill_price(price)
    end_cash = qty * sell_fill_price(price)
    expected = start_cash * (1 - SLIPPAGE) / (1 + SLIPPAGE)
    assert abs(end_cash - expected) < 1e-9, "Fee/slippage matematika ne odgovara formuli."
    assert end_cash < start_cash, "Round-trip uz naknade/slippage ne smije povećati kapital na konstantnoj cijeni."
    print(f"PASS check_fee_arithmetic: {start_cash} -> {end_cash:.4f} na konstantnoj cijeni (FEE={FEE}, SLIPPAGE={SLIPPAGE}).")


def check_ohlc_integrity(pair: str, candles: list[Candle]) -> None:
    """Osnovna provjera kvalitete podataka: nema duplikata, nema nemogućih OHLC odnosa, nema
    negativnih/nultih cijena."""
    seen = set()
    for c in candles:
        assert c.opened_at not in seen, f"{pair}: duplikat svijeće na {c.opened_at}"
        seen.add(c.opened_at)
        assert c.open > 0 and c.high > 0 and c.low > 0 and c.close > 0, f"{pair}: nepozitivna cijena na {c.opened_at}"
        assert c.high >= max(c.open, c.close), f"{pair}: high manji od open/close na {c.opened_at}"
        assert c.low <= min(c.open, c.close), f"{pair}: low veći od open/close na {c.opened_at}"
    print(f"PASS check_ohlc_integrity: {pair}, {len(candles)} svijeća, bez duplikata/nemogućih OHLC odnosa.")


def main() -> None:
    conn = db.get_connection()
    try:
        btc = load_candles(conn, "binance", "BTC/USDT", 1440, 0, 2_000_000_000)
        assert len(btc) > CUTOFF_INDEX + 50, "Nema dovoljno BTC/USDT svijeća za check_no_lookahead."

        check_ohlc_integrity("BTC/USDT", btc)
        check_fee_arithmetic()
        check_no_lookahead(btc)
        print("SVE PROŠLO.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
