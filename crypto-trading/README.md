# Kripto trgovanje — istraživački MVP

Aplikacija za istraživanje i (opcionalno, kasnije) automatizaciju trgovanja kriptovalutama na
Coinbaseu. Nastala je na temelju istraživačkog paketa korisnika (SQLite baza povijesnih cijena +
backtest alat, vidi `data/`) i proširena na: usporedbu više strategija, paper trading na živim
cijenama, i (isključeno po defaultu) slanje pravih naloga.

## Ključni nalaz od kojeg se kreće

Priloženi istraživački paket sadržavao je jedno testirano pravilo (kupi na dnevni signal rasta od
2%) koje je na BTC/EUR, 2024-01-01 do 2026-11-21, **izgubilo novac**: 500 € → 108,41 €, maksimalni
pad 79,11%. Ovaj MVP to pravilo zadržava kao `baseline_2pct` isključivo kao referentnu, ne
preporučenu, točku — backtest engine je provjeren da daje identičan rezultat (vidi "Kako je
provjereno" ispod).

Tri nove strategije su dodane da bi se moglo tražiti nešto bolje: `sma_crossover`, `rsi_meanrev`,
`dip_buy_volume`. Na istom razdoblju (BTC/EUR, 2024–2026), `sma_crossover` s parametrima
fast=5/slow=20 je u ovom jednom testu nadmašio i baseline i "buy & hold" (908 € nasuprot 710 € za
buy&hold i 108 € za baseline). **Ovo NIJE dokaz trajne prednosti** — uzorak ima svega ~26 trgovina
na jednom paru u jednom (uglavnom rastućem) tržišnom razdoblju, što je premalo da se isključi
slučajnost ili da se zaključi da će raditi i ubuduće. Koristi dashboard (odjeljak 1) da testiraš
više parova, razdoblja i parametara prije nego ičemu vjeruješ.

## Arhitektura

- **`data/kripto.sqlite`** — povijesne dnevne/5-min svijeće (Binance, Coin Metrics, uzorci
  Kraken/Coinbase/OKX), preuzeto iz priloženog paketa. `data/schema.sql` je izvorna shema;
  `data/schema_extra.sql` dodaje tablice za backtest/paper/live runove bez diranja povijesnih
  podataka.
- **`app/backtest.py`** + **`app/strategies/`** — generički dnevni backtest engine (odluka nakon
  zatvaranja dana, izvršenje na idućem otvaranju) i strategije. Svaka strategija je čista funkcija
  `(context) -> "buy"/"sell"/"hold"`, pa se identičan kod koristi i za backtest i za paper/live.
- **`app/coinbase_client.py`** — javni cjenovni feed (bez ključa) i autenticirani Advanced Trade
  API klijent (CDP API ključ, ES256 JWT).
- **`app/paper_engine.py`** — pozadinska nit po pokrenutom runu, svakih 5 min provjerava je li
  stigla nova zatvorena dnevna svijeća, simulira trgovinu po živoj cijeni (isti troškovni model kao
  backtest), stanje uvijek rekonstruira iz zabilježenih trgovina (preživi restart servera).
- **`app/live_engine.py`** — identična logika, ali šalje prave naloge. Vidi sigurnosne mehanizme
  ispod.
- **`static/`** — dashboard (čisti HTML/CSS/JS, bez vanjskih ovisnosti, radi i bez interneta osim
  za Coinbase pozive).

## Pokretanje

```bash
cd crypto-trading
python3 -m venv .venv && source .venv/bin/activate   # preporučeno - izbjegava sukobe sa sustavskim Python paketima
pip install -r requirements.txt
cp .env.example .env   # po potrebi uredi (Coinbase ključ, live postavke)
uvicorn app.main:app --reload --port 8010
```

Otvori [http://localhost:8010](http://localhost:8010).

## Kako je provjereno

Backtest engine je testiran tako da `baseline_2pct` na BTC/EUR, 2024-01-01 do 2026-11-21, daje
**točno** isti rezultat kao priloženi izvještaj (165 trgovina, 47 profitabilnih, 108,41 € završni
saldo, 79,11% maksimalni pad) — vidi `rezultat_testa.json` u izvorno priloženom paketu. Ovo
potvrđuje da čitanje podataka i troškovni model (0,1% slippage + 0,4% naknada po strani) rade
ispravno prije nego im se vjeruje za nove strategije.

**Coinbase integracija (javni feed, autenticirani pozivi, format naloga) NIJE uživo testirana** —
ovo razvojno okruženje nema izlazni pristup internetu prema Coinbaseu. Prije stvarnog korištenja:
1. Pokreni server negdje s normalnim internet pristupom.
2. Klikni "Testiraj vezu" (odjeljak 2 dashboarda) — ako javi grešku, popravak je izoliran u
   `app/coinbase_client.py` (endpoint, JWT format, nazivi polja u odgovoru).
3. Pokreni paper trading i prati barem nekoliko dana/tjedana prije nego razmišljaš o live modu.

## Sigurnosni mehanizmi za live trgovanje

Live trgovanje je **isključeno po defaultu** i namjerno zahtijeva više koraka da se uključi:

1. `.env`: `LIVE_TRADING_ENABLED=false` po defaultu. Mora se ručno postaviti na `true`.
2. `.env`: `LIVE_MAX_POSITION_EUR` ograničava koliko EUR jedan "buy" nalog smije potrošiti - mora
   biti > 0, inače `live_engine` odbija pokrenuti run.
3. `.env`: `LIVE_DAILY_LOSS_LIMIT_EUR` - ako dnevni (od ponoći UTC) neto gubitak premaši ovaj iznos,
   run se automatski zaustavlja (novi "buy" nalozi se odbijaju, otvorena pozicija se još uvijek
   smije zatvoriti). Ako odgovor Coinbasea ne sadrži očekivano polje za izračun gubitka, sustav
   **iz opreza pretpostavlja da je limit probijen** i zaustavlja run, umjesto da tiho nastavi.
4. Dashboard ne nudi "Pokreni live trgovanje" gumb dok ručno ne potvrdiš checkbox da razumiješ da
   se koristi pravi novac.
5. Live runovi se **ne nastavljaju automatski** nakon restarta servera (za razliku od paper
   runova) - potrebno ih je ručno ponovno pokrenuti. Ovo je namjerno, ne propust.
6. API ključ za Coinbase napravi s dopuštenjem **samo za trgovanje**, nikad za podizanje sredstava
   ("withdraw"/"transfer") - tako je šteta u slučaju kompromitacije ključa ograničena.

Nijedan od ovih mehanizama nije zamjena za tvoju vlastitu procjenu rizika. Ovo je razvojni kod,
nije uživo testiran protiv pravog Coinbase računa, i trgovanje kriptovalutama može dovesti do
potpunog gubitka uloženih sredstava.

## Ograničenja koja treba znati

- Strategije su long-only na spotu (kupi/drži/prodaj) - nema shortanja ni poluge.
- Paper i live trgovanje donose odluke na dnevnim svijećama dohvaćenim uživo s Coinbasea, ne iz
  statične `data/kripto.sqlite` baze (ta baza se koristi samo za backtest).
- `dip_buy_volume` i `rsi_meanrev` su u jedinom dosad pokrenutom testu izgubili novac - uključene
  su kao alat za daljnje istraživanje, ne kao preporuka.
- Format Coinbase Advanced Trade API odgovora (posebno polja u odgovoru na nalog korištena za
  izračun dnevnog P&L-a: `filled_value` / `total_value_after_fees`) nije potvrđen uživo - ako se
  pokaže da polje ne postoji, `LIVE_DAILY_LOSS_LIMIT_EUR` provjera će (namjerno, fail-safe)
  zaustaviti run umjesto da ga tiho zaobiđe; svejedno provjeri `app/live_engine.py` prvom prilikom
  s pravim pristupom.
