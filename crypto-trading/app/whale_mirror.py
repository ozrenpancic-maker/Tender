"""'Whale mirror' - zrcali promjene stanja JAVNOG on-chain ETH novčanika u simuliranom (paper)
portfelju. Balans adrese je po definiciji javan podatak u lančanom registru - nema tu ničije
privatnosti za narušiti, za razliku od pokušaja kopiranja anonimnih trgovaca s burzovnih
"leaderboard" stranica (vidi README zašto je TAJ put napušten: nema stvarnog javnog API-ja, a
burze ne objavljuju povijest tuđih pozicija ni kad bi se do API-ja i došlo).

KAKO RADI: svaki `POLL_INTERVAL_SECONDS` provjeri trenutno ETH stanje praćene adrese (Etherscan).
Usporedi s zadnje zabilježenim stanjem:
- stanje JAKO POVEĆALO (>= threshold_pct) i NISMO u poziciji -> KUPI (zrcali "akumulaciju")
- stanje JAKO SMANJILO (>= threshold_pct, u minus) i JESMO u poziciji -> PRODAJ (zrcali "distribuciju")
- inače ništa (ili već smo u poziciji koja odgovara smjeru, ili nema pozicije za zatvoriti)

Svaka trgovina je SVE ILI NIŠTA (cijela gotovina / cijela pozicija) - isto kao i većina ostalih
strategija u ovom projektu. Ne pokušavamo proporcionalno kopirati IZNOS (praćeni novčanik ima
veličinu reda $10k-$1M+, naš simulirani bot $100-1000 - proporcionalno kopiranje iznosa bi bilo
besmisleno, kopiramo SMJER).

POŠTENO OGRANIČENJE: balans adrese se mijenja i iz razloga koji NEMAJU veze s "trgovanjem" (gas
naknade za obične transakcije, premještanje između vlastitih novčanika, staking, NFT kupnje...).
Ovo je heuristički proxy za "whale aktivnost", NE provjeren trgovački signal - vidi README za
potpuno objašnjenje i zašto je prag (threshold_pct) bitan (filtrira sitan "šum" od naknada).

NEMA POVIJESNOG BACKTESTA - ne postoji besplatan izvor povijesnih stanja/velikih transakcija za
proizvoljnu adresu unatrag (Etherscan daje SAMO trenutno stanje i popis transakcija, ne "stanje na
dan X" bez prolaska kroz svaku transakciju ručno). Ovo je ČISTO uživo praćenje od trenutka
pokretanja nadalje - promatraj ga, nemoj mu vjerovati unaprijed."""
import threading
import time

from app import coinbase_client, db, etherscan_client
from app.costs import TAKER_FEE, taker_buy_fill, taker_sell_fill

POLL_INTERVAL_SECONDS = 600  # on-chain stanja se ne mijenjaju na sekundu - 10 min je dovoljno često

_active_runs: dict[int, threading.Event] = {}
_lock = threading.Lock()


def _mark_to_market(run: dict, eth_price_bid: float) -> float:
    if not run["in_position"]:
        return run["cash"]
    return run["cash"] + run["quantity_base"] * taker_sell_fill(eth_price_bid) * (1 - TAKER_FEE)


def _tick(run_id: int) -> None:
    conn = db.get_connection()
    try:
        run_row = conn.execute("SELECT * FROM whale_mirror_run WHERE id=? AND status='running'", (run_id,)).fetchone()
        if not run_row:
            return
        run = dict(run_row)
        now = int(time.time())

        try:
            whale_balance_eth = etherscan_client.get_eth_balance(run["address"])
        except etherscan_client.EtherscanError as err:
            print(f"[whale_mirror] run {run_id}: Etherscan greška ({err}) - pokušat ću sljedeći tick.")
            return

        try:
            ticker = coinbase_client.get_public_ticker(coinbase_client.to_product_id(run["pair"]))
        except Exception as err:
            print(f"[whale_mirror] run {run_id}: ne mogu dohvatiti cijenu za {run['pair']} ({err}).")
            return

        equity = _mark_to_market(run, ticker["bid"])
        conn.execute(
            "INSERT OR REPLACE INTO whale_mirror_equity_point (run_id, at, equity, whale_balance_eth) VALUES (?, ?, ?, ?)",
            (run_id, now, round(equity, 4), round(whale_balance_eth, 6)),
        )
        conn.commit()

        last_wei = int(run["last_whale_balance_wei"]) if run["last_whale_balance_wei"] else None
        current_wei = int(round(whale_balance_eth * 1e18))

        if last_wei is None or last_wei == 0:
            # Prvi tick (ili je novčanik bio prazan) - samo zabilježi baznu liniju, bez trgovine.
            conn.execute("UPDATE whale_mirror_run SET last_whale_balance_wei=? WHERE id=?", (str(current_wei), run_id))
            conn.commit()
            return

        delta_pct = (current_wei - last_wei) / last_wei
        threshold = run["threshold_pct"]

        if delta_pct >= threshold and not run["in_position"]:
            fill = taker_buy_fill(ticker["ask"])
            quantity = (run["cash"] * (1 - TAKER_FEE)) / fill
            conn.execute(
                "UPDATE whale_mirror_run SET cash=0, in_position=1, quantity_base=?, entry_price=?, last_whale_balance_wei=? WHERE id=?",
                (quantity, fill, str(current_wei), run_id),
            )
            conn.execute(
                "INSERT INTO whale_mirror_trade (run_id, side, price, amount_usd, whale_balance_eth, whale_delta_pct, executed_at)"
                " VALUES (?, 'buy', ?, ?, ?, ?, ?)",
                (run_id, fill, round(run["cash"], 4), round(whale_balance_eth, 6), round(delta_pct, 4), now),
            )
        elif delta_pct <= -threshold and run["in_position"]:
            fill = taker_sell_fill(ticker["bid"])
            proceeds = run["quantity_base"] * fill * (1 - TAKER_FEE)
            conn.execute(
                "UPDATE whale_mirror_run SET cash=?, in_position=0, quantity_base=0, entry_price=NULL, last_whale_balance_wei=? WHERE id=?",
                (proceeds, str(current_wei), run_id),
            )
            conn.execute(
                "INSERT INTO whale_mirror_trade (run_id, side, price, amount_usd, whale_balance_eth, whale_delta_pct, executed_at)"
                " VALUES (?, 'sell', ?, ?, ?, ?, ?)",
                (run_id, fill, round(proceeds, 4), round(whale_balance_eth, 6), round(delta_pct, 4), now),
            )
        else:
            conn.execute("UPDATE whale_mirror_run SET last_whale_balance_wei=? WHERE id=?", (str(current_wei), run_id))
        conn.commit()
    finally:
        conn.close()


def _loop(run_id: int, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            _tick(run_id)
        except Exception as err:  # ne smije srušiti server zbog privremene greške
            print(f"[whale_mirror] run {run_id}: neočekivana greška: {err}")
        stop_event.wait(POLL_INTERVAL_SECONDS)


def start_run(label: str, address: str, pair: str, starting_balance: float, threshold_pct: float) -> int:
    address = address.strip()
    if not address.startswith("0x") or len(address) != 42:
        raise ValueError("Adresa mora biti standardna ETH adresa (0x + 40 hex znakova).")
    if not 0 < threshold_pct < 1:
        raise ValueError("threshold_pct mora biti između 0 i 1 (npr. 0.03 = 3%).")
    if starting_balance <= 0:
        raise ValueError("starting_balance mora biti pozitivan.")

    # Provjeri da adresa i par stvarno rade PRIJE pokretanja (poštenije nego pokrenuti run koji
    # odmah tiho ne radi ništa).
    etherscan_client.get_eth_balance(address)
    coinbase_client.get_public_ticker(coinbase_client.to_product_id(pair))

    conn = db.get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO whale_mirror_run (label, address, pair, starting_balance, threshold_pct, cash, started_at, status)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 'running')",
            (label, address, pair, starting_balance, threshold_pct, starting_balance, int(time.time())),
        )
        conn.commit()
        run_id = cur.lastrowid
    finally:
        conn.close()

    stop_event = threading.Event()
    with _lock:
        _active_runs[run_id] = stop_event
    threading.Thread(target=_loop, args=(run_id, stop_event), daemon=True).start()
    return run_id


def stop_run(run_id: int) -> None:
    with _lock:
        stop_event = _active_runs.pop(run_id, None)
    if stop_event:
        stop_event.set()
    conn = db.get_connection()
    try:
        conn.execute("UPDATE whale_mirror_run SET status='stopped', stopped_at=? WHERE id=?", (int(time.time()), run_id))
        conn.commit()
    finally:
        conn.close()


def resume_running_on_startup() -> None:
    conn = db.get_connection()
    try:
        rows = conn.execute("SELECT id FROM whale_mirror_run WHERE status='running'").fetchall()
    finally:
        conn.close()
    for row in rows:
        stop_event = threading.Event()
        with _lock:
            _active_runs[row["id"]] = stop_event
        threading.Thread(target=_loop, args=(row["id"], stop_event), daemon=True).start()
