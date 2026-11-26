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


def _mutate_future_volatility(candles: list[Candle], from_index: int) -> list[Candle]:
    """Kao _mutate_future, ali mijenja VOLATILNOST budućnosti (naizmjence x1.25 / x0.8 po svijeći).
    Potrebno jer obično množenje cijelog niza s 3 ne mijenja log-povrate - procjena volatilnosti
    koja (pogrešno) viri u budućnost to ne bi primijetila. Nađeno namjernim ubacivanjem buga: prva
    verzija check_portfolio_no_lookahead s običnim 3x je PROŠLA s volatilnošću koja gleda 5 dana unaprijed."""
    out = list(candles[:from_index])
    for k, c in enumerate(candles[from_index:]):
        f = 1.25 if k % 2 == 0 else 0.8
        out.append(replace(c, open=c.open * f, high=c.high * f, low=c.low * f, close=c.close * f, volume=c.volume * 5))
    return out


def check_portfolio_no_lookahead(candles_by_pair: dict[str, list[Candle]]) -> None:
    """Isto kao check_no_lookahead, ali za sloj odluka portfelja (app/portfolio_backtest.py):
    signali, procjene volatilnosti i ciljne težine (s i bez ciljanja volatilnosti portfelja) na
    datumima prije reza moraju biti identični bez obzira na promjenu budućnosti NA SVIM PAROVIMA."""
    from app.portfolio_backtest import DEFAULT_STRATEGIES, compute_target_weights

    first = next(iter(candles_by_pair.values()))
    start_ts = first[300].opened_at
    cutoff_ts = first[CUTOFF_INDEX].opened_at
    nonzero_dates = 0
    for mutate in (_mutate_future, _mutate_future_volatility):
        mutated = {}
        for p, cs in candles_by_pair.items():
            cut = next(i for i, c in enumerate(cs) if c.opened_at >= cutoff_ts)
            mutated[p] = mutate(cs, cut)

        for target_vol in (None, 0.3):
            a = compute_target_weights(candles_by_pair, DEFAULT_STRATEGIES, start_ts, target_vol)
            b = compute_target_weights(mutated, DEFAULT_STRATEGIES, start_ts, target_vol)
            before = [(x, y) for x, y in zip(a, b) if x[0] < cutoff_ts]
            assert before, "check_portfolio_no_lookahead: nema datuma prije reza - test ne bi ništa provjerio."
            for (t, w_a, s_a, v_a), (_, w_b, s_b, v_b) in before:
                same = (
                    s_a == s_b
                    and v_a.keys() == v_b.keys() and all(abs(v_a[p] - v_b[p]) < 1e-12 for p in v_a)
                    and all(abs(w_a[p] - w_b[p]) < 1e-12 for p in w_a)
                )
                assert same, (
                    f"LOOK-AHEAD BUG u portfelju ({mutate.__name__}, target_vol={target_vol}): "
                    f"odluka na {t} ovisi o budućim podacima."
                )
                nonzero_dates += any(w > 0 for w in w_a.values())
    # Bez ovoga bi test mogao "proći" samo zato što su sve težine 0 u testiranom razdoblju.
    assert nonzero_dates > 0, "check_portfolio_no_lookahead: sve težine prije reza su 0 - test težina ništa ne dokazuje."
    print(f"PASS check_portfolio_no_lookahead: {len(candles_by_pair)} para, {len(before)} datuma prije reza, "
          f"2 vrste mutacije budućnosti (cijena i volatilnost), s i bez ciljanja volatilnosti.")


def check_fee_arithmetic() -> None:
    """Konstantna cijena, jedna kupnja i jedna prodaja: naknade+slippage mogu SAMO smanjiti kapital,
    nikad ga povećati ili ostaviti netaknutim.

    VAŽNO (nađeno u ChatGPT-ovoj neovisnoj reviziji): prva verzija ovog testa koristila je samo
    `buy_fill_price`/`sell_fill_price` (SLIPPAGE), bez FEE - test bi prošao i kad bi stvarna
    naknada u `run_generic_backtest` imala grešku, jer je provjeravao samo pola troškovnog modela.
    Formula ispod sada vjerno ponavlja ONO ŠTO SIMULACIJA STVARNO RADI
    (`app/backtest.py:run_generic_backtest` - `cash*(1-FEE)/buy_fill` pri kupnji,
    `position*sell_fill*(1-FEE)` pri prodaji), ne samo costs.py helper funkcije izolirano."""
    price = 100.0
    start_cash = 100.0
    position_base = (start_cash * (1 - FEE)) / buy_fill_price(price)
    end_cash = position_base * sell_fill_price(price) * (1 - FEE)
    expected = start_cash * (1 - FEE) / (1 + SLIPPAGE) * (1 - SLIPPAGE) * (1 - FEE)
    assert abs(end_cash - expected) < 1e-9, "Fee/slippage matematika ne odgovara formuli iz backtest.py."
    assert end_cash < start_cash, "Round-trip uz naknade/slippage ne smije povećati kapital na konstantnoj cijeni."
    only_slippage = start_cash * (1 - SLIPPAGE) / (1 + SLIPPAGE)
    assert end_cash < only_slippage, "Stvarni trošak mora biti veći (kapital manji) nego da FEE ne postoji."
    print(f"PASS check_fee_arithmetic: {start_cash} -> {end_cash:.4f} na konstantnoj cijeni (FEE={FEE}, SLIPPAGE={SLIPPAGE}), potvrđeno veći trošak nego samo-slippage ({only_slippage:.4f}).")


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

        eth = load_candles(conn, "binance", "ETH/USDT", 1440, 0, 2_000_000_000)
        cutoff_plus = btc[CUTOFF_INDEX + 30].opened_at  # skraćeno - test treba samo okolinu reza, ne cijelu povijest
        check_portfolio_no_lookahead({
            "BTC/USDT": [c for c in btc if c.opened_at <= cutoff_plus],
            "ETH/USDT": [c for c in eth if c.opened_at <= cutoff_plus],
        })
        print("SVE PROŠLO.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
