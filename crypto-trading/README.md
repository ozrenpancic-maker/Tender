# Kripto trgovanje — istraživački MVP

Aplikacija za istraživanje i (opcionalno, kasnije) automatizaciju trgovanja kriptovalutama na
Coinbaseu. Nastala je na temelju istraživačkog paketa korisnika (SQLite baza povijesnih cijena +
backtest alat, vidi `data/`) i proširena na: usporedbu više strategija, paper trading na živim
cijenama, i (isključeno po defaultu) slanje pravih naloga.

## Analiza konkretnog portfelja (XRP, SUI, PEPE, DOGE...)

Korisnik je podijelio stvarni Binance portfolio: ~$288 ukupno, gotovo sve pozicije duboko u minusu
(XRP -70%, SUI -85%, PEPE -79%, DOGE -85%, POL -92%, ALGO -95%, AMP -99%...). Zatraženo je da se
pokuša aktivno oporaviti kroz trgovanje, ali bez automatskog spajanja na pravi Binance račun za
sada - samo analiza/backtest.

**Bitno iskreno upozorenje**: ništa u ovoj aplikaciji ne može obećati "veliki profit kroz vrijeme"
od portfelja koji je ovoliko u minusu - to bi bilo prazno obećanje. `app/binance_history_client.py`
dodaje mogućnost dohvaćanja povijesti za BAŠ te coinove (izvorna baza je imala samo BTC/ETH/SOL),
da bi se strategije mogle pošteno testirati na njima umjesto nagađanja. Čim se sinkroniziraju
(dashboard, odjeljak 3), odmah su dostupni u backtestu/optimizatoru (odjeljci 4 i 7) jer koriste
isti `candle` format - ništa se drugo ne mijenja u kodu. Dodan je i **odjeljak 2 "Signali
kupi/prodaj"** (i odjeljak 1 "AI Prediction Engine" - vidi ispod) koji direktno odgovara na pitanje
"kad kupiti/prodati koji coin" - vidi nove sekcije ispod.

Napomene specifične za ove coinove:
- PEPE i SUI su mladi (2023.) - mnogo kraća povijest za testiranje znači manje statističke snage;
  bilo koji "dobar" rezultat na njima treba gledati sa znatno više skepse nego na BTC/ETH.
- "Dust" pozicije (SOL $0.03, ETH $0.01, AMP, JASMY - ispod par centi u ovom portfelju) namjerno
  nisu uključene u popis za automatski sync - trgovanje njima bi izgubilo više na naknadama
  (0,4% + 0,1% slippage po strani, vidi `app/costs.py`) nego što sama pozicija vrijedi.
- POL je Binance simbol nakon Polygon rebranda (bivši MATIC) - ako "Testiraj vezu" javi grešku za
  njega, Binance možda još uvijek koristi stari simbol za taj par, provjeri i ispravi u
  `PORTFOLIO_PAIRS`.

## AI Prediction Engine (`app/ml/`, dashboard odjeljak 1)

KriptoMVP 4.4 faza 3 - ML model (LightGBM + logistička regresija kao kontrola) koji za 4 neovisna
horizonta (1h/4h/24h/7d) vraća **kalibrirane** vjerojatnosti P(up)/P(down)/P(sideways) (zbrajaju se
na 100%), AI Score (0-100, ocjena KVALITETE I SMJERA signala, ne izravna vjerojatnost rasta - vidi
formula ispod), kategoriju (STRONG SELL...STRONG BUY po pragovima iz specifikacije), razloge za/
protiv, i procjenu kvalitete podataka. Ovo je ODVOJENO od jednostavnog rule-based `app/signals.py`
(dashboard odjeljak 2) - oba ostaju, dashboard ih prikazuje kao dvije različite stvari s različitim
razinama pouzdanosti.

### Metodologija (bitno za povjerenje u rezultat, ne samo za kod)

1. **Značajke** (`app/ml/features.py`) - 20 tehničkih indikatora po svijeći (RSI14, Stoch RSI,
   MACD histogram, udaljenost od EMA9/21/50/200 i SMA20/50/200, ATR normaliziran, percentil
   volatilnosti, Bollinger %b i širina, ROC na 3 duljine, relativni volumen, udaljenost od
   20-svijeća maksimuma/minimuma). Svaka značajka na indeksu `i` koristi ISKLJUČIVO svijeće
   `[0..i]` - nema gledanja unaprijed.
2. **Label** (`app/ml/labels.py`) - 3 klase (up/down/sideways). Granica između klasa NIJE fiksni
   postotak, nego `max(trošak_round_trip ≈1%, 0.5 × ATR_normaliziran × √broj_koraka)` - veća je kad
   je tržište volatilnije i kad je horizont dulji, manja kad je mirno. Label na indeksu `i` gleda
   `candles[i + steps_ahead].close` - to je JEDINO mjesto u cijelom pipelineu gdje se gleda
   unaprijed, namjerno odvojeno od značajki.
3. **Walk-forward validacija** (`app/ml/dataset.py`) - podaci (pooled BTC/ETH/SOL/XRP, parovi se
   NE kodiraju kao značajka) podijeljeni kronološki u foldove; za svaki fold: train (expanding
   window) → zadnjih 20% toga je kalibracijski skup (izolirana kalibracija vjerojatnosti preko
   `CalibratedClassifierCV` s izotoničnom regresijom) → test na SLJEDEĆEM, još neviđenom bloku, uz
   `purge_seconds` čišćenje granice (vidi "Druga runda" ispod). Nijedan test primjer nikad nije
   korišten za fit ili kalibraciju bilo kojeg modela koji ga predviđa.
4. **Kalibracija i poštena provjera** (`app/ml/calibration.py`) - Brier score (multiklasni),
   log loss, reliability dijagram (pouzdanost vs stvarna točnost po binovima), i NAIVNA bazna
   linija (model koji uvijek predviđa udio klasa iz treninga, "ne znam ništa"). Model se smatra
   **validiranim** samo ako je njegov Brier score barem 2% relativno bolji od bazne linije na
   walk-forward testu (pravilo #12/#13: nevalidiran model ne aktivira live preporuku).

### Rezultat treniranja nakon pravog internet pristupa (23.11.2026. - vidi "Četvrta runda" ispod)

Prva verzija (113 dana resampliranih 1h/4h podataka) nije validirala NIŠTA. Nakon što je okruženju
dopušten izlazni internet pristup, sinkronizirana je PRAVA 3-godišnja 1h/4h povijest (ne resample)
za BTC/ETH/SOL/XRP preko `app/binance_vision_client.py` - uzorak je narastao 14-18x:

| Horizont | Uzorak (n) | LightGBM Brier | Bazna linija Brier | Validiran? |
|---|---|---|---|---|
| 1h | 106.524 (prava 1h povijest, 3 god., 4 para) | 0,1798 | 0,1916 | **DA** ✅ (6,1% bolji) |
| 4h | 26.028 (prava 4h povijest, 3 god., 4 para) | 0,4202 | 0,4295 | **DA** ✅ (2,2% bolji) |
| 24h | 11.383 (prava dnevna povijest + XRP) | 0,5135 | 0,5137 | NE |
| 7d | 11.359 (prava dnevna povijest + XRP) | 0,5509 | 0,5437 | NE |

**Prvi put u ovom projektu model stvarno validira** - za 1h i 4h horizont. `/api/predictions` za
te horizonte sada vraća PRAVU kalibriranu predikciju (P(up)/P(down)/P(sideways), AI Score, BUY/
WAIT/SELL), ne automatski WAIT. 24h/7d i dalje vraćaju WAIT, konzistentno s ranijim nalazom da je
dnevni/tjedni horizont teži za ovaj feature-set.

**Poštena napomena o marginalnosti**: 4h prolazi s 2,2% poboljšanjem, tik iznad 2% pragova - to je
"prolazi, ali ne s velikom rezervom", ne "dokazano pouzdano". Prag postoji baš da takve granične
slučajeve ne proglasi lažno sigurnima bez daljnje provjere (npr. paper trading kroz stvaran budući
period). 1h ima više prostora (6,1%), nešto čvršći rezultat.

### AI Score formula (transparentna, ne "crna kutija")

```
AI Score = round(100 × P(up) + 50 × P(sideways) + 0 × P(down))
```

Linearna skala: siguran "up" = 100, siguran "sideways" = 50 (WAIT zona), siguran "down" = 0. Ovo je
ocjena kvalitete+smjera, NE izravna vjerojatnost rasta (pravilo #7) - vjerojatnosti su u `p_up`/
`p_down`/`p_sideways` poljima odgovora, odvojeno. Kategorije po specifikaciji: 0-25 STRONG SELL,
26-45 SELL, 46-55 WAIT, 56-75 BUY, 76-100 STRONG BUY.

### Kako ponovno trenirati

```bash
cd crypto-trading && source .venv/bin/activate
pip install lightgbm scikit-learn joblib shap   # ako već nisu instalirani
python3 -m app.ml.train
```

Zapisuje `data/models/<horizont>_lgbm.joblib` i `data/models/metadata.json` (walk-forward metrike,
`validated` zastavica koju `app/ml/engine.py` čita). Siguran je za ponovno pokretanje - briše i
ponovno piše iste datoteke, ne mijenja ništa drugo u bazi.

### Automatsko ponovno treniranje (`app/ml/retrain_scheduled.py`)

Korisnik je pitao za "AI učenje" iz novih podataka uživo. Pravo "online learning" (model se mijenja
sam od sebe iz svake nove opservacije u stvarnom vremenu) je NAMJERNO odbačeno - prerizično je
(model bi se mogao tiho pogoršati, a label za "je li cijena porasla za 1h" se saznaje tek za 1h, pa
nema stvarne prednosti brzine). Umjesto toga: periodično ponovno treniranje s **sigurnosnom
"promotion gate"** - potpuno drugačiji, već dokazan pristup u kvantitativnim financijama:

1. Osvježi zadnjih ~400 dana povijesnih svijeća za sve ML parove/intervale (`app/binance_history_client`).
2. Treniraj svaki horizont u PRIVREMENI (staging) direktorij - uživo model još netaknut.
3. Usporedi walk-forward Brier score kandidata s trenutnim uživo modelom.
4. **Promoviraj (zamijeni uživo model) SAMO ako kandidat nije gori** - niže je bolje. Ako je gori,
   ili ako kandidat IZGUBI validaciju koju je prijašnji model imao, stari model ostaje na snazi,
   NEMA tihog pogoršanja.
5. Zapiše jedan redak u `data/models/retrain_log.jsonl` (append, ne prepisuje) sa svakom odlukom i
   zašto - vidljivo na dashboardu (odjeljak 1, "Automatsko ponovno treniranje").

Pokreni ručno: `python3 -m app.ml.retrain_scheduled` (ili gumb "Pokreni ponovno treniranje sad" na
dashboardu). Napomena: `app/ml/engine.py` sad provjerava datum izmjene (mtime) datoteka modela i
metapodataka prije svake predikcije - promovirani model se primjenjuje ODMAH, bez potrebe za
restartom servera.

**Postavljanje tjednog automatskog pokretanja (Windows Task Scheduler)**:

1. Napravi `retrain.bat` u `crypto-trading` folderu sa sadržajem (prilagodi putanju ako treba):
   ```bat
   @echo off
   cd /d C:\kripto\Tender\crypto-trading
   .venv\Scripts\python.exe -m app.ml.retrain_scheduled >> data\models\retrain_console.log 2>&1
   ```
2. Otvori **Task Scheduler** (Win+R → `taskschd.msc`).
3. **Create Task...** (ne "Basic Task" - treba više opcija):
   - General: ime npr. "Kripto AI retrain", "Run whether user is logged on or not".
   - Triggers → New: Weekly, odaberi dan/vrijeme (npr. nedjelja 03:00 - kad server sigurno nije
     zauzet drugim stvarima).
   - Actions → New: Program/script = puna putanja do `retrain.bat`.
   - Conditions: isključi "Start the task only if the computer is on AC power" ako je mini PC uvijek
     na struji (jest, to mu je namjena).
4. Testiraj odmah desnim klikom → "Run", provjeri `data\models\retrain_console.log` i
   `data\models\retrain_log.jsonl` da je prošlo bez greške.

**Pošteno ograničenje**: ovo zahtijeva da `uvicorn` server bude kasnije ponovno pokrenut barem
jednom da pokupi python kod promjene (ako ih bude) - sam retrain POGAĐA žive modele datoteke dok
server radi (zato mtime provjera gore), ne treba restart SAMO za novi model, ALI ako se ikad
promijeni kod `app/ml/` modula, treba.

### Razlozi za/protiv (`reasons_for`/`reasons_against`)

Koriste `shap.TreeExplainer` nad stvarnim LightGBM modelom (izvučenim iz `CalibratedClassifierCV`
omota) - PRAVI doprinosi značajki TOJ KONKRETNOJ predikciji, ne interpretacija vrijednosti
značajke. Odgovor uvijek ima `reasons_method` ("shap" ili "heuristic_fallback") - stara
heuristika (jednostavna pravila, npr. "RSI14 < 30 → razlog za") ostaje kao fallback ako SHAP iz
nekog razloga ne uspije.

### Uživo dohvat podataka: Coinbase, ne Binance

Model je TRENIRAN na Binance podacima (`app/binance_vision_client.py`), ali UŽIVO predikcija
dohvaća najnoviju cijenu/svijeću s **Coinbase-a** (`app/coinbase_client.py`), ne s Binancea -
Binance REST API je geografski blokiran iz ovog razvojnog okruženja (vidi "Četvrta runda" ispod).
'BTC/USDT' se mapira na Coinbaseov 'BTC-USD' - USDT i USD su stablecoin/fiat s razlikom tipično
ispod 0,1%, prihvatljiva aproksimacija JER je svaka značajka u modelu omjer/postotak (RSI,
EMA-udaljenost...), nikad apsolutna cijena u određenoj valuti. Coinbase nema izravnu 4h
granulaciju - za "4h" horizont dohvate se 1h svijeće (paginirano, Coinbase ograničava na ~300
svijeća po pozivu) i agregiraju u 4h (`resample_candles`).

**Popravljena greška (bila je stvarni uzrok "404" grešaka koje su se vidjele u produkciji)**:
`app/coinbase_client.to_product_id()` je prije samo radio `pair.replace("/", "-")`, tj. 'SUI/USDT'
-> 'SUI-USDT' - ali Coinbase **nema** -USDT par za svaki coin u portfelju. Uživo provjereno: SUI,
PEPE, POL i ALGO postoje na Coinbaseu SAMO kao -USD (vraćaju HTTP 404 na -USDT), dok BTC/XRP/DOGE/
NEAR imaju oba pa se razlika dosad nije primijetila. Funkcija sad uvijek zamijeni USDT→USD prije
slanja Coinbaseu (isto što `app/signals.py` već radi nezavisno) - ovo je popravilo live cijene za
Paper trading i Automatizirani paper trading na ta četiri coina.

## Signali kupi/prodaj (`app/signals.py`, dashboard odjeljak 2)

Korisnik je tražio da aplikacija izravno kaže "kad kupiti koji kripto i kada prodati", u dva
horizonta: kratkoročno (2h do par dana) i dugoročno (3+ mjeseca). Prije gradnje, kratkoročni dio je
STVARNO testiran (ne pretpostavljen) na jedinom pravom skupu podataka koji za to imamo: priloženi
paket sadrži prave 5-minutne svijeće za BTC/ETH/SOL od 2026-08-01 do 2026-11-21 (113 dana), koje su
agregirane u 4h svijeće (`interval_min=240` u `candle` tablici, iste pravo-povijesne, ne izmišljene).

**Nalaz**: prave kratkoročne (satne/par-dnevne) mehaničke konfiguracije - RSI mean-reversion, brzi
SMA presjek (12h/36h) - dosljedno su GUBILE novac na sva 4 para, uglavnom zbog naknada (0,4% +
0,1% slippage po strani) pri prečestom trgovanju (briza varijanta: 48 trgovina u 113 dana, pad do
52%). Sporiji `sma_crossover` (fast=12/slow=48, u satima ~2 dana/8 dana) pobjeđivao je "kupi i drži"
na sva 4 para, ali s nijansiranim obrascem potvrđenim i u in-sample (kolovoz-sredina listopada,
snažan uspon) i out-of-sample (sredina listopada-studeni, pad) dijelu: GUBIO je dio dobiti tijekom
uspona, ali DRAMATIČNO ograničio gubitak tijekom pada (pad portfelja od svega 0-12% umjesto 30-38%
za buy&hold). To je svjestan, objašnjiv kompromis (manja gornja granica dobiti za puno manji rizik
pada), ne "pobjeđuje uvijek" - i stvarna učestalost trgovanja bila je otprilike jednom svakih 1-2
tjedna po paru, ne doslovno svaka 2 sata.

**Zašto `dip_buy_volume` NIJE korišten unatoč dobrom rezultatu u prvom testu**: ta strategija pamti
kada je "ušla u poziciju" kroz uzastopne pozive unutar backtest petlje (`ctx.params["_entry_index"]`)
da zna kad je prošao `hold_days`. Za ŽIVI signal ne postoji ta povijest poziva - ne znamo kad si ti
stvarno kupio pojedini coin - pa bi uvjet izlaska bio neupotrebljiv/pogrešan izvan backtesta. Zato
`app/signals.py` namjerno koristi samo STATELESS strategije (presjek dviju pokretnih prosjeka,
izračunljiv iz same trenutne i prethodne svijeće, bez potrebe za pamćenjem povijesti poziva).

**Kako radi**: `compute_signal(pair, horizon)` dohvaća najnovije svijeće uživo (Coinbase, bez
ključa - vidi "Četvrta runda" niže zašto ne Binance) i pokreće `decide()` ISTE funkcije koja se
koristi u backtestu, dva puta - jednom s
`in_position=True` (tvoja stvarna situacija za sve coinove iz portfelja - daje DRŽI/PRODAJ) i jednom
s `in_position=False` (da dokupljuješ/ponovno ulaziš - daje ČEKAJ/KUPI). Nema posebne logike za
"live" - identičan kod kao backtest, samo pozvan jednom na zadnju svijeću umjesto u petlji.

**Presets**:
- Kratkoročno: `sma_crossover` fast=12/slow=48 na 4h svijećama, testiran kako je opisano gore.
- Dugoročno: `sma_crossover` fast=10/slow=40 na dnevnim svijećama - isti default kao ostatak
  aplikacije (vidi "Pretraga po više parova" ispod), testiran na BTC/ETH/SOL kroz puni ciklus
  2022-2026, NIJE testiran specifično na XRP/SUI/PEPE/DOGE/POL/NEAR/ALGO.

**I dalje vrijedi**: ovo su mehanički signali iz koda koji može biti u krivu, ne preporuke
financijskog savjetnika. Kratkoročni preset nije testiran na konkretnim coinovima iz portfelja -
samo na BTC/ETH/SOL. "Osvježi signale" radi uživo (Coinbase, potvrđeno) - svih 7 portfolio coinova
(XRP, SUI, PEPE, DOGE, POL, NEAR, ALGO) su uživo testirani dostupni.

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
slučajnost ili da se zaključi da će raditi i ubuduće. Koristi dashboard (odjeljak 4) da testiraš
više parova, razdoblja i parametara prije nego ičemu vjeruješ.

Dodane su i dvije strategije s makro kontekstom: `equity_filtered` (isti SMA presjek, ali 'buy' je
dopušten samo kad je S&P 500 iznad svog 50-dnevnog prosjeka) i `multi_macro_filter` (isto, plus
zahtijeva da zlato NIJE u naglom skoku - tipičan znak "bijega u sigurnost"/risk-off raspoloženja).
Obje testiraju ideju da kripto cijene dobrim dijelom prate opće tržišno raspoloženje. Trebaju
sinkronizirane S&P 500 / zlato podatke (dashboard, odjeljak 5) prije pokretanja backtesta; bez toga
bacaju jasnu grešku umjesto da tiho zanemare filter.

### Širi popis čimbenika (tehnička analiza, makro, sentiment, regulativa, fundamentalno)

Dodane su dvije daljnje strategije i šest novih izvora podataka, prema opsežnom popisu čimbenika
("tehnička analiza, order book, kitovi, on-chain, sentiment, makroekonomija, ETF tokovi,
fundamentalna analiza, tokenomics, regulativa") koji bi napredni kripto trading sustav trebao
razmatrati. Nisu dodane sve kategorije - neke (order book dubina, praćenje "kitova", on-chain
metrike poput MVRV/SOPR) zahtijevaju plaćene pretplate (Glassnode/Nansen/CryptoQuant) ili
infrastrukturu za koju trenutno nema opravdanja bez takve pretplate; vidi popis "Namjerno
izostavljeno" niže.

**`technical_composite`** - kombinira EMA200 trend filter, MACD presjek i OBV (volumen) potvrdu
umjesto oslanjanja na jedan indikator. Ne treba nove vanjske podatke (čista matematika nad
postojećim svijećama). Konzistentno niži maksimalni pad od `sma_crossover` na istom razdoblju
(2022-2026: 24-40% umjesto 44-67%), uz mješovite rezultate po paru (profitabilan na 3 od 4 testirana
para, gubi na SOL/USDT) - vidi `app/indicators.py` za sve dodane indikatore (EMA, MACD, Stochastic
RSI, ROC, OBV, ATR, Bollinger Bands).

**`macro_signal_composite`** - obavezan EMA200 trend gate plus glasovanje 4 neovisna signala (Fed
stopa ne raste, Reddit sentiment, regulatorni skor, ETF tokovi) - kupnja samo ako dovoljno glasova
kaže "risk-on". Nedostajući podatak se ne broji ni za ni protiv (ne nagađa se). Treba sve 4 serije
sinkronizirane (dashboard, odjeljak 6) prije backtesta.

Novi besplatni/sivo-područje izvori (dashboard, odjeljak 6; detalji i env varijable u "Pokretanje"):

| Izvor | Što daje | Cijena | Pouzdanost |
|---|---|---|---|
| FRED | Fed stopa, CPI, nezaposlenost, BDP, M2 novčana masa, prinosi na obveznice (10Y, realni) | Besplatno (treba ključ) | Službeni API, visoka |
| DeFiLlama | TVL po chainu (Ethereum, Solana) | Besplatno, bez ključa | Službeni API, visoka |
| CoinGecko | Implicitna cirkulirajuća ponuda (market cap / cijena) | Besplatno, bez ključa, rate-limited | Službeni API, visoka |
| Binance futures | Funding rate (BTC/ETH/SOL perpetuali) - povijest godinama unatrag | Besplatno, bez ključa | Službeni API, visoka |
| GitHub | Broj commitova (razvojna aktivnost) za zadani repo | Besplatno, bez ključa (60/h) ili s PAT (5000/h) | Službeni API, visoka |
| Google Trends | Interes za pretrage ("bitcoin", "crypto") | Besplatno, neslužbeno (pytrends) | **Niska** - Google često mijenja zaštite, može prestati raditi bez najave |
| Reddit | Grub leksikonski sentiment (r/Bitcoin, r/CryptoCurrency) | Besplatno (treba app registraciju) | Srednja - leksikon je grub, nije NLP model |
| CryptoPanic | Stvarni glasovi zajednice (bullish/bearish) po objavi | Besplatno (treba registraciju) | Srednja - API je mijenjao verzije u prošlosti |
| ETF tokovi | Dnevni neto tok BTC/ETH spot ETF-ova | Besplatno, scraping (farside.co.uk) | **Niska** - HTML scraping, krhko |
| Regulativa | Leksikonski skor SEC/CFTC RSS objava | Besplatno, RSS | Srednja - leksikon je grub, ne pravna analiza |

**Ispravak u odnosu na raniju procjenu**: prije sam praćenje derivata (funding rate, open interest,
likvidacije) svrstao pod "treba plaćenu pretplatu" zajedno s order book dubinom. To je bilo
pregrubo - **povijest funding ratea je besplatno dostupna** (Binance Futures javni API, bez ključa,
godinama unatrag), pa je iskoristiva i za backtest, ne samo uživo promatranje. Dodana je nova
strategija `derivatives_extremes` (kontrarijanski "short/long squeeze" signal - kupi na ekstremno
negativan funding, izađi na ekstremno pozitivan) koja to koristi. Open interest je i dalje ograničen
na zadnjih ~30 dana od strane Binancea (`app/binance_derivatives_client.py:fetch_open_interest`) -
dovoljno za paper/live uvid, ne za dugi backtest, pa nije uključen u formalni `needs_series` sustav.

**Namjerno izostavljeno** (provjereno ili jaka indikacija da zahtijeva plaćenu pretplatu za API
pristup, ne samo web sučelje): Glassnode (besplatni tier je u međuvremenu sveden na web grafove, ne
API), CryptoQuant, IntoTheBlock, Token Terminal, CoinAnk (whale tracking i on-chain izvedene metrike
poput MVRV/NVT/SOPR/exchange in-outflow), i order book dubina/zidovi (javno dostupno uživo preko
Coinbase websocketa, ali **nema besplatnih povijesnih order book podataka** pa se ne bi moglo ni
backtestirati, samo uživo promatrati). Trading Economics ima besplatan tier, ali vrlo ograničen i
uglavnom se preklapa s FRED-om (koji je pouzdaniji za američke podatke) - nije dodan. Ako želiš
nešto od ovoga, javi koji servis planiraš platiti pa se dogradi integracija s tim API ključem.

### Zašto "pronađi profitabilnu strategiju" nije tako jednostavno kako zvuči

Dodan je **optimizator s in-sample/out-of-sample provjerom** (dashboard, odjeljak 7; `app/optimizer.py`)
jer je ručno biranje parametara dok rezultat na JEDNOM razdoblju ne izgleda dobro klasičan "curve
fitting" - gotovo uvijek postoji neka kombinacija koja na papiru izgleda sjajno čistom slučajnošću.
Konkretan primjer iz ovog projekta: `sma_crossover` optimiziran na 2024–2025 (in-sample) daje
odlične rezultate (npr. fast=10/slow=20: 500 € → 837 €), ali ISTI parametri na 2026. (out-of-sample,
podaci koje optimizacija nije vidjela) daju 500 € → **480 €**, tj. gubitak. Od 5 najboljih in-sample
kombinacija, nijedna nije ponovila uspjeh izvan uzorka - sve su ili izgubile novac ili jedva ostale u
plusu. Ovo nije propust u kodu, nego iskren i očekivan rezultat: **dosad testirane kombinacije na
ovom paru/razdoblju nisu pokazale pouzdanu prednost koja preživljava izvan uzorka na kojem je
pronađena.** Prije nego se bilo čemu ovdje vjeruje s pravim novcem, treba naći kombinaciju koja
radi dobro na OBA razdoblja (dashboard to jasno označava), i dalje uz svijest da ni to nije jamstvo.

### Pretraga po više parova i razdoblja — najjači dosadašnji nalaz

Pretraga je proširena na sva 4 dostupna para (BTC/EUR, BTC/USDT, ETH/USDT, SOL/USDT) i više
razdoblja (2022–2026, po godinama, uključujući medvjeđe tržište 2022.). Nalazi:

- `dip_buy_volume` nije bio profitabilan izvan uzorka ni u jednom od 8 testiranih kombinacija
  para/razdoblja. `rsi_meanrev` samo u 1 od 8. `sma_crossover` je jedina strategija koja je dosljedno
  prolazila oba testa na više parova.
- Svaka testirana kombinacija parametara gubi novac u 2022. na svim parovima - očekivano za
  strategiju koja prati trend, jer je 2022. bila produženo medvjeđe tržište (Terra/Luna, FTX).
  Ovo nije slučajnost specifična za jedan par, nego dosljedan obrazac.
- Fiksna kombinacija **fast=10/slow=40** (sad je to default za `sma_crossover`) testirana je kao
  JEDAN neprekinuti backtest 2022-01-01 do 2026-11-21 (puni ciklus pad-oporavak-rast) na sva 4 para,
  bez ponovnog optimiziranja parametara za svaki par:

  | Par | SMA(10/40) | Buy & Hold | Max pad (strategija / hold) |
  |---|---|---|---|
  | BTC/EUR | 709 € | 672 € | 48% / 64% |
  | BTC/USDT | 729 € | 648 € | 50% / 67% |
  | ETH/USDT | 1.208 € | 228 € | 44% / 74% |
  | SOL/USDT | 2.075 € | 206 € | 67% / 95% |

  (Svi rezultati od 500 € početnog ulaganja, uključujući naknade/slippage.) Strategija nadmašuje
  buy&hold na sva 4 para, uvijek uz manji maksimalni pad - mehanizam je da filter trenda izbacuje iz
  pozicije tijekom produženih padova, pa izbjegne dio štete od sloma 2022. (ETH/SOL buy&hold izgubio
  je tad >50% vrijednosti).

  **Ograničenja ovog nalaza, ne uljepšana verzija:**
  - Prednost na BTC parovima je skromna (709 vs 672 €, 729 vs 648 €) - veći dio "pobjede" dolazi od
    ETH-a i SOL-a, koji su 2022. pali posebno teško. Sljedeći medvjeđi ciklus ne mora pogoditi iste
    parove jednako teško.
  - `fast=10/slow=40` nije izabran iz potpuno "slijepog" testa - odabran je jer se pokazao
    najdosljedniji u ranijoj godišnjoj/in-sample-out-of-sample pretrazi, pa je ovaj test potvrda tog
    nalaza na punom razdoblju, ne nova, potpuno neviđena provjera.
  - 2022-2026 je jedan uzorak tržišne povijesti (jedan ciklus). Max pad je i dalje 44-67% - ovo je
    "manje loše od kupi-i-drži", ne "bez rizika".
  - Backtest i dalje nije isto što i live trgovanje (vidi odjeljak "Kako je provjereno" ispod).

## Nezavisna provjera s ChatGPT-ovim paralelnim istraživanjem (KriptoMVP 5.1)

Korisnik je dao ChatGPT-u isti `data/kripto.sqlite` (iz ovog projekta) da napravi odvojeni,
nezavisno napisani backtest paket (`backtest_51.py` i srodne skripte - nije dio ovog repozitorija,
samo pregledano). Vrijedno je zapisati rezultat te usporedbe:

- **Metodologija se uglavnom poklapa**: odluka nakon zatvaranja svijeće, izvršenje na idućem
  otvaranju, identičan trošak (0,4% naknada + 0,1% slippage po strani), razvoj parametara samo na
  2021-2024, provjera na 2025-2026 bez ponovnog podešavanja. ChatGPT-ov paket ima i automatski test
  za look-ahead bias (promijeni buduće podatke, provjeri da se prošli signal ne mijenja) - dobra
  praksa koja je prevedena i u ovaj projekt, vidi `app/checks.py` ispod.
- **Portirane su nove strategije** (`app/strategies/trend_guard.py`, `ema_trend.py`,
  `confirmed_trend.py`, `donchian_breakout.py`, `dual_momentum.py`, `vol_guarded_trend.py`) iz
  njihovog koda, prevedene u ovog projekta `decide(ctx)` oblik. **Cross-validacija**: `trend_guard`
  (fast=10/slow=40/trend=100) na BTC/ETH/SOL, 2025-01-01 do 2026-11-21, 100 USDT, dao je **točno**
  102,41 / 151,94 / 96,76 - identično njihovim brojevima, do centa. To je jaka potvrda da oba
  nezavisna backtest motora (različit jezik stila, ista logika) ispravno implementiraju istu
  metodologiju.
- **Usput otkriven i popravljen pravi bug** u `run_backtest`: generički put nije učitavao povijest
  PRIJE `start_ts`, pa su strategije s dugim lookbackom (SMA100/200) bile "slijepe" prvih
  100-200 dana TRAŽENOG razdoblja umjesto da koriste već postojeću stvarnu povijest prije njega.
  Cross-validacija je to otkrila (brojevi se nisu poklapali dok fix nije dodan) - popravljeno je
  dodavanjem "zagrijavajućeg" baffera prije `start_ts` koji se koristi samo za indikatore, ne za
  stvarno trgovanje (portfelj uvijek kreće ravno, bez pozicije, na traženi `start_ts` - ista
  konvencija kao u ChatGPT-ovom paketu). Ovo popravlja preciznost SVIH strategija s dugim
  lookbackom, ne samo novih.
- **Njihov glavni nalaz (konzistentan s ovim projektom)**: trend-praćenje s regime-filterom
  smanjuje max pad naspram kupi-i-drži (32-38% umjesto 63%) uz skroman profit ili gubitak ovisno o
  coinu - nije dokazana prednost, kompromis rizika. Njihova "rotacija u najjaču valutu" strategija
  izgledala je izvrsno na 2021-24 (+448%, +196%, +91%) ali se **srušila** na 2025-26 (-46,72%) -
  klasičan primjer overfittinga na jedan povijesni režim; **ne koristiti za uživo signale** (oboje
  se slažemo). Njihov kratki 1h/4h test (38 dana) je uglavnom negativan nakon troškova - isti
  zaključak kao kratkoročna istraživanja u ovom projektu.
- **Ograničenje nezavisnosti koje i ChatGPT sam ističe**: razdoblje 2025-2026 NIJE potpuno "čisto"
  neviđeno za obje strane - prije ovog testa je već bilo analizirano u razgovoru s korisnikom
  (uključujući pad njegovog stvarnog portfelja), pa postoji blagi rizik data-snoopinga i za ovaj
  projekt i za ChatGPT-ov. Vrijedi uzeti u obzir pri tumačenju "pobjeđuje kupi-i-drži" nalaza.

### Druga runda revizije (KriptoMVP 5.2) - pet pravih bugova, svi popravljeni

ChatGPT je napravio drugu, dublju neovisnu reviziju ("REVIZIJA_KriptoMVP_5_2.md") nad ovim kodom (ne
samo usporedbu rezultata) i pronašao pet konkretnih bugova, svi popravljeni u ovom repozitoriju:

1. **(Kritično) Uživo AI dohvat premalo povijesti** (`app/ml/engine.py`): formula
   `days=max(30, interval_min // 60)` za 24h/7d horizont dohvaćala je samo 30 dnevnih svijeća, a
   validacija zahtijeva barem 210 - ta tri horizonta bi ostala zauvijek blokirana (WAIT) čak i
   nakon uspješne validacije modela. Popravljeno: dohvaća se dovoljno dana za barem 230 ZATVORENIH
   svijeća na odgovarajućem intervalu, uz 10 dana rezerve.
2. **(Kritično) ML curenje oznaka preko granice test bloka** (`app/ml/dataset.py`): label na
   trenutku t koristi cijenu na t+horizont. Bez čišćenja, zadnji primjeri u kalibracijskom skupu
   imali su label čiji je ishod zapravo bio POZNAT tek nakon početka test bloka - blaga
   kontaminacija. Popravljeno dodavanjem `purge_seconds` parametra koji izbacuje iz treninga/
   kalibracije svaki primjer čiji label-prozor seže u ili preko početka test bloka. Nakon popravka:
   walk-forward Brier rezultati ostali su gotovo identični (0,52605 vs 0,52504 na 24h, 0,56738 vs
   0,55622 na 7d) - curenje je postojalo, ali nije promijenilo zaključak. **Cross-validacija**:
   ChatGPT-ova neovisna implementacija istog popravka dala je 0,52579/0,52504 (24h) i 0,56753/
   0,55622 (7d) - baseline Brier identičan do 5 decimala, LightGBM Brier razlika <0,0002.
3. **(Kritično) Nedovršena posljednja svijeća u uživo dohvatu** (`app/binance_history_client.py`):
   `fetch_recent` nije izbacivao svijeću koja je još "u tijeku" - model je treniran na ZATVORENIM
   svijećama, pa bi djelomična posljednja svijeća (volumen/close se još mijenjaju) unijela razmak
   između treninga i uživo ulaza. Popravljeno.
4. **(Visok) Provjera naknada testirala samo slippage** (`app/checks.py`): `check_fee_arithmetic`
   je koristio samo `buy_fill_price`/`sell_fill_price` (SLIPPAGE), ne i FEE - test bi prošao i da
   je stvarna naknada u `run_generic_backtest` imala grešku. Popravljeno da vjerno prati STVARNU
   formulu iz backtesta. **Cross-validacija**: ispravan rezultat na 100 USDT, konstantna cijena,
   jedna kupnja+prodaja = **99,0034** - identično ChatGPT-ovom neovisnom izračunu, do 4 decimale.
5. **(Visok) Zastarjeli podaci nisu blokirali BUY/SELL** (`app/ml/engine.py`): kvaliteta podataka
   se računala i vraćala u odgovoru, ali decision/AI Score su se i dalje računali i prikazivali čak
   i kad je zadnja svijeća bila zastarjela. Popravljeno - zastarjeli podaci sada prisilno vraćaju
   "NEMA DOVOLJNO POUZDANIH PODATAKA" umjesto moguće krive preporuke na staroj cijeni.

Dodatno je pronađen i stvaran sigurnosni propust koji je **već prije ove revizije bio poznat i
opisan** u ovom README-u (vidi "Ograničenja koja treba znati"), a sada je i popravljen: dashboard
API nije imao NIKAKVU autentikaciju. Dodan je opcionalni `DASHBOARD_API_KEY` (vidi `.env.example`)
- ako je postavljen, svi `/api/*` pozivi moraju imati `Authorization: Bearer <ključ>`; ako nije
postavljen (default), ponašanje je nepromijenjeno. Dashboard ima jednostavno polje za unos ključa
(pamti se u localStorage preglednika).

### Treća runda - preostale stavke s popisa (4 riješene, 3 blokirane sandboxom)

- ✅ **Point-in-time dostupnost makro podataka** (`app/macro_store.py`, `data/schema_extra.sql`):
  `macro_series` je imao samo `observed_date` (dan NA KOJI se podatak odnosi), ne dan kad je
  STVARNO postao dostupan - teoretski curenje (strategija bi "znala" vrijednost prije objave).
  Dodan `available_date` stupac (automatska migracija za postojeću bazu u `app/db.py`), izveden
  kao `observed_date + LAG_DAYS[source]` (npr. FRED +1 dan, Google Trends +2 dana, dnevni
  sentiment agregati +1 dan - jer se cijeli dan mora završiti prije agregacije). `load_series`
  sada filtrira po `available_date`, ne `observed_date`. **NAPOMENA O POUZDANOSTI**: LAG_DAYS su
  konzervativne procjene, NISU provjerene uživo protiv stvarnog kalendara objave svakog izvora
  (nema pristupa internetu) - vidi dokumentaciju u `macro_store.py`.
- ✅ **Usporediv završni obračun likvidacije** (`app/backtest.py`): equity curve (i za buy_hold i
  za generičke strategije) sada na SVAKOJ točki računa stvarnu gotovinu da bi se likvidiralo SADA
  (`sell_fill_price` + naknada), ne sirovu mark-to-market cijenu - ista konvencija kao ChatGPT-ov
  `sim_hold`. Usput je nađena i popravljena mala nedosljednost: `run_buy_hold` je prije koristio
  drugu (približno, ne identično jednaku) formulu za trošak kupnje nego `run_generic_backtest`.
  Cross-validacija (`trend_guard`, BTC/ETH/SOL, 2025-2026) nepromijenjena - 102,41/151,94/96,76 do
  centa, jer su ti specifični testovi završili bez otvorene pozicije.
- ✅ **Realne naknade kao scenarij, ne fiksna pretpostavka** (`app/costs.py`, nova ruta
  `/api/backtest/cost-sensitivity`, dashboard odjeljak 4 "Test osjetljivosti na naknade"): isti
  backtest se sada može pokrenuti preko 5 imenovanih scenarija (zadano, Coinbase Advanced Trade
  niski/visoki volumen, Coinbase "jednostavna" Buy/Sell tipka, pesimističan). **Konkretan nalaz**:
  `trend_guard` na BTC/USDT 2025-26 je profitabilan na 4 od 5 scenarija, ali **gubi novac**
  (85,54 € od 100 €) na scenariju "Coinbase jednostavna tipka" (~1,49% efektivni spread) - dokaz
  da profitabilnost nekih strategija ovisi o tome koristi li se najjeftiniji način trgovanja, ne
  samo o samoj strategiji. Orijentacijski brojevi, NISU uživo provjereni protiv trenutnog Coinbase
  cjenika - vidi napomenu u `app/costs.py`.
- ✅ **SHAP objašnjenja umjesto heuristike** (`app/ml/engine.py`): `reasons_for`/`reasons_against`
  sada koriste `shap.TreeExplainer` nad stvarnim LightGBM modelom (izvučenim iz
  `CalibratedClassifierCV` omota) za PRAVE doprinose značajki TOJ KONKRETNOJ predikciji, ne
  interpretaciju vrijednosti značajki. Stara heuristika je ostala kao fallback (`reasons_method`
  u odgovoru govori koja je metoda stvarno korištena) ako SHAP iz nekog razloga ne uspije.
- ✅ **1h/4h pokrivenost** i ✅ **XRP puna povijest** - RIJEŠENO u "Četvrtoj rundi" ispod, nakon što
  je okruženju dopušten izlazni internet pristup.
- ✅ **Mrežni pozivi i Android APK build** - RIJEŠENO, vidi "Četvrta runda" ispod.

### Četvrta runda - pravi internet pristup dopušten (23.11.2026.)

Korisnik je ovom okruženju dopustio izlazni internet pristup i pregled svih domena. Rezultat: 2 od
3 prethodno "trajno blokirane" stavke su genuinski riješene, plus niz drugih poboljšanja koja to
otkriva.

**Binance REST API je geografski blokiran (HTTP 451) - ovo NIJE problem s internet pristupom.**
`api.binance.com` i `fapi.binance.com` odbijaju ovu lokaciju/IP po Binanceovim Uvjetima korištenja,
neovisno o tome ima li okruženje internet - vidi napomenu u `app/binance_history_client.py` i
`app/binance_derivatives_client.py`. **ALI `data.binance.vision` (statična bulk arhiva povijesnih
svijeća, isti podaci kao REST API, samo unaprijed spremljeni u ZIP/CSV arhive po mjesecu) NIJE pod
istim ograničenjem i radi normalno** - uživo potvrđeno. Novi `app/binance_vision_client.py`
koristi upravo to:

- **Puna XRP/USDT dnevna povijest** sinkronizirana (2018-05 do danas, 3125 svijeća) - prvi put u
  ovom projektu. XRP je uključen u pooled ML trening (vidi iznad) i dostupan za backtest/strategije.
- **Prava 3-godišnja 1h i 4h povijest** (ne resample iz 113 dana 5-min podataka) za BTC/ETH/SOL/
  XRP, sinkronizirana od 2023-11 (26.832 1h-svijeća i 6.708 4h-svijeća po paru). Zamjenjuje
  prijašnji resample pristup u `app/ml/dataset.py`.
- **Usput otkriven i popravljen pravi bug**: Binance je neke exportove 2025.+ prebacio s
  MILIsekundnih na MIKROsekundne vremenske oznake (upravo to na što je izvorna specifikacija
  upozoravala) - stariji monthly arhivi (2024.) koriste 13-znamenkaste (ms) vrijednosti, noviji
  daily arhivi (2026.) 16-znamenkaste (µs). `_to_seconds()` u `binance_vision_client.py` razlikuje
  po veličini broja (>10^14 = µs), ne po datumu arhive (sigurnije po redu podataka, ne po
  pretpostavci).

**Uživo dohvat je prebačen s Binancea (blokiran) na Coinbase (radi)** - i za AI Prediction Engine
(`app/ml/engine.py`) i za rule-based Signali kupi/prodaj (`app/signals.py`). Svih 7 korisnikovih
portfolio coinova (XRP, SUI, PEPE, DOGE, POL, NEAR, ALGO) su uživo potvrđeni dostupni na Coinbaseu
(`{COIN}-USD`). `app/coinbase_client.py` proširen s proizvoljnom granulacijom
(`get_public_candles`) i paginacijom preko Coinbaseovog limita od ~300 svijeća po pozivu
(`get_public_candles_paginated`) - potreban za 4h (dohvat 1h + resample) i dulje "long" preset
razdoblje (400 dana).

**ML rezultat** (vidi "AI Prediction Engine" iznad za detalje): nakon ponovnog treniranja na
pravoj, puno većoj povijesti, **1h i 4h horizont prvi put validiraju**. 24h i 7d i dalje ne.

**Android APK se stvarno izgradio** - prije se samo pisalo da Gradle postoji, ali Android SDK
nije bio instaliran. Preuzet je `commandlinetools` + `platform-34` + `build-tools;34.0.0` preko
`sdkmanager` (dl.google.com dostupan), `gradle assembleDebug` je prošao, APK je potpisan
(debug ključ) i provjeren (`aapt dump badging`, `apksigner verify`) - stvaran, instalabilan
`app-debug.apk` (5,6 MB), poslan korisniku. Ovo i dalje NIJE release/produkcijski potpisan build
niti testiran na stvarnom uređaju (nema Android emulatora/uređaja u ovom okruženju) - samo prvi
put stvarno POTVRĐENO da se projekt kompajlira i pakira u instalabilan APK.

**Ostali klijenti, uživo testirani prvi put (vidi dokumentaciju u svakoj datoteci za detalje)**:

| Klijent | Status |
|---|---|
| `coinbase_client.py` | ✅ radi |
| `defillama_client.py` | ✅ radi |
| `coingecko_client.py` | ✅ radi |
| `trends_client.py` (Google Trends) | ✅ radi |
| `regulatory_client.py` (SEC/CFTC RSS) | ✅ radi |
| `fred_client.py` | ⚠️ treba besplatan API ključ (nepromijenjeno) |
| `reddit_client.py` | ⚠️ treba besplatan client ID/secret (nepromijenjeno) |
| `cryptopanic_client.py` | ⚠️ treba besplatan API ključ (nepromijenjeno) |
| `binance_history_client.py`, `binance_derivatives_client.py` | ❌ Binance geografski blokira ovu lokaciju (HTTP 451) - vidi gore |
| `etf_client.py` (farside.co.uk) | ❌ Cloudflare bot-zaštita (403, JS-challenge) - treba headless preglednik, ne `httpx` |
| `github_client.py` | ❌ OVO SPECIFIČNO sandbox okruženje blokira izravne REST pozive prema api.github.com (traži korištenje vlastitog GitHub alata) - na korisnikovom računalu bi trebalo raditi normalno |
| `equity_client.py` (Stooq) | ❌ Veza se prekida na razini proxyja (TLS handshake timeout), ne čist HTTP odbijaj - nije dalje istraživano |

## Arhitektura

- **`data/kripto.sqlite`** — povijesne dnevne/5-min svijeće (Binance, Coin Metrics, uzorci
  Kraken/Coinbase/OKX), preuzeto iz priloženog paketa. `data/schema.sql` je izvorna shema;
  `data/schema_extra.sql` dodaje tablice za backtest/paper/live runove bez diranja povijesnih
  podataka.
- **`app/backtest.py`** + **`app/strategies/`** — generički dnevni backtest engine (odluka nakon
  zatvaranja dana, izvršenje na idućem otvaranju) i strategije. Svaka strategija je čista funkcija
  `(context) -> "buy"/"sell"/"hold"`, pa se identičan kod koristi i za backtest i za paper/live.
- **`app/checks.py`** — integritetski testovi (ne profitabilnost): look-ahead bias (mijenja buduću
  svijeću, provjerava da se prošla odluka ne mijenja, za SVE registrirane strategije), aritmetika
  naknada/slippagea, OHLC integritet podataka (duplikati, nemogući odnosi). Pokreni
  `python3 -m app.checks` nakon svake nove/izmijenjene strategije. Vidi "Nezavisna provjera s
  ChatGPT-ovim paralelnim istraživanjem" iznad. Od portfelja nadalje provjerava i sloj odluka
  portfelja (`check_portfolio_no_lookahead`).
- **`app/portfolio_backtest.py`** — portfelj trend strategija preko više coinova (ansambl 3
  strategije, veličina po inverznoj volatilnosti, opcionalno ciljanje volatilnosti). Odluke
  (`compute_target_weights`) odvojene od izvršenja zbog provjere look-aheada. Vidi "Portfelj trend
  strategija" ispod.
- **`app/coinbase_client.py`** — ISKLJUČIVO javni cjenovni feed (bez ključa). Autenticirani dio je
  uklonjen (KriptoMVP 4.4 pravila) - vidi "Isključivo savjetnik/simulator" ispod.
- **`app/ml/`** — AI Prediction Engine (faza 3): `features.py` (značajke), `labels.py` (3-klasni
  label, trošak+volatilnost-skalirana granica), `dataset.py` (pooled BTC/ETH/SOL, walk-forward
  foldovi), `calibration.py` (Brier/log loss/reliability + bazna linija), `train.py` (LightGBM +
  logistička regresija), `engine.py` (uživo predikcija, WAIT gate za nevalidirane horizonte). Vidi
  "AI Prediction Engine" iznad.
- **`app/equity_client.py`** — dnevni podaci za S&P 500 / Dow / Nasdaq / zlato sa Stooq-a (javno,
  bez ključa), za makro-filter strategije. `app/aux_candles.py` poravnava kripto (trguje se 7 dana u tjednu)
  i equity/zlato (zatvoreno vikendom) kalendare uzimanjem zadnje poznate cijene na/prije danog dana.
  (Datoteka se zvala `app/aux.py` do 25.11.2026. - `aux` je rezervirano ime na Windowsu (kao `con`,
  `prn`, `nul`), pa `git clone` nikad nije mogao zapisati tu datoteku na disk na Windows serveru -
  nađeno uživo pri postavljanju korisnikovog Windows servera, preimenovano odmah.)
- **`app/binance_history_client.py`** — povijest cijena za proizvoljan Binance par i interval
  (1d/4h/1h) preko REST API-ja, izravno u `candle` tablicu (source_id='binance') - isti oblik kao
  izvorni podaci. Geografski blokiran iz OVOG razvojnog okruženja (HTTP 451) - vidi
  `app/binance_vision_client.py` za trenutno korišten izvor.
- **`app/binance_vision_client.py`** — statična bulk arhiva povijesnih svijeća
  (data.binance.vision, monthly/daily ZIP+CSV) - NIJE geografski blokirana, koristi se za punu
  XRP povijest i pravu 1h/4h povijest za ML trening. Vidi "Četvrta runda" iznad.
- **`app/signals.py`** — trenutni (uživo) signal kupi/prodaj po dva horizonta, koristi iste
  `decide()` funkcije kao backtest, pozvane jednom na zadnju svijeću umjesto u petlji. Vidi
  "Signali kupi/prodaj" iznad.
- **`app/indicators.py`** — čiste funkcije za EMA, MACD, Stochastic RSI, ROC, OBV, ATR, Bollinger
  Bands - bez vanjskih poziva, koriste ih `technical_composite` i `macro_signal_composite`.
- **`app/macro_store.py`** + `macro_series` tablica — generička pohrana ne-OHLC serija (jedna
  vrijednost po danu), zajednička za sve nove makro/sentiment izvore. `app/aux_candles.py` ima odgovarajuće
  pomoćne funkcije (`series_value_on_or_before`, `series_change_pct`) za ovaj oblik podataka.
- **`app/fred_client.py`**, **`app/defillama_client.py`**, **`app/coingecko_client.py`**,
  **`app/trends_client.py`**, **`app/reddit_client.py`**, **`app/etf_client.py`**,
  **`app/regulatory_client.py`**, **`app/binance_derivatives_client.py`**, **`app/github_client.py`**,
  **`app/cryptopanic_client.py`** — po jedan klijent po izvoru, svaki s istim sučeljem
  (`fetch_recent`, `sync_to_db`, `test_connection`). `app/macro_clients.py` je registar koji ih
  povezuje po imenu izvora - koristi ga paper/live engine i API rute.
- **`app/optimizer.py`** — grid search parametara na in-sample razdoblju + provjera top 5 na
  out-of-sample razdoblju, radi smanjenja (ne eliminacije) rizika od curve fittinga.
- **`app/paper_engine.py`** — pozadinska nit po pokrenutom runu, svakih 5 min provjerava je li
  stigla nova zatvorena dnevna svijeća, simulira trgovinu po živoj cijeni (isti troškovni model kao
  backtest), stanje uvijek rekonstruira iz zabilježenih trgovina (preživi restart servera).
- **`app/auto_trader.py`** — automatizirani multi-coin paper trading: isti obrazac pozadinske niti
  kao `paper_engine.py`, ali odluku o KOJEM coinu umjesto fiksne strategije donosi AI Prediction
  Engine (`app/ml/engine.py`), rangirajući cijeli univerzum parova po AI Score-u svaki sat/4h. Vidi
  "Automatizirani paper trading" iznad.
- **`static/`** — dashboard (čisti HTML/CSS/JS, bez vanjskih ovisnosti, radi i bez interneta osim
  za Coinbase/Stooq pozive).

## Pokretanje

```bash
cd crypto-trading
python3 -m venv .venv && source .venv/bin/activate   # preporučeno - izbjegava sukobe sa sustavskim Python paketima
pip install -r requirements.txt
cp .env.example .env   # po potrebi uredi (opcionalni ključevi za makro/sentiment izvore)
uvicorn app.main:app --reload --port 8010
```

Otvori [http://localhost:8010](http://localhost:8010).

**Dashboard se sad sam osvježava** - "AI Prediction Engine", "Signali kupi/prodaj", "Paper trading"
i "Automatizirani paper trading" se učitaju automatski pri otvaranju stranice (ne treba više ručno
kliknuti "Osvježi" u svakoj sekciji posebno) i ponovno svakih 60 sekundi dok je stranica otvorena.
Gumb "Osvježi sve" u zaglavlju odmah pokreće sve četiri odjednom. Testovi veze i sinkronizacije
(Coinbase, Wall Street, makro izvori, Binance povijest) ostaju ručni - to su mrežno/vremenski skuplje
radnje s nuspojavama (upis u bazu), namjerno se ne pokreću same.

**Dashboard je organiziran u 4 taba** (umjesto 11 odjeljaka nabacanih jedan ispod drugog): "Pregled"
(AI Prediction Engine + Signali - ono što svakodnevno provjeravaš, zadano otvoren), "Trgovanje"
(Paper trading + Automatizirani paper trading), "Analiza" (Backtest usporedba + Optimizator),
"Podaci i veze" (sinkronizacija portfelja, Wall Street, makro/sentiment izvori, Coinbase veza).
Zadnje otvoren tab se pamti (localStorage) - stranica se sljedeći put otvori na istom mjestu. Duži
objašnjavajući tekstovi po odjeljku su sklonjeni iza "ℹ️ Što ovo znači" sklopivog izbornika (sadržaj
je identičan, samo nije nabačen u lice prije nego vidiš gumbe/tablicu) - poštene napomene o
ograničenjima nisu izgubljene, samo nisu zadane vidljive.

## Android (instalacija na telefon preko lokalne mreže)

Dashboard je postavljen kao PWA (manifest + ikone + service worker, vidi `static/manifest.json` i
`static/sw.js`) pa ga je moguće instalirati na Android telefon kao app - bez Play Storea, bez
Android Studija. Backend i dalje mora raditi na računalu; telefon mu pristupa preko WiFi-ja.

1. Pokreni server tako da sluša na cijeloj mreži, ne samo na računalu:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8010
   ```
   Ovo čini server dostupnim svima na istoj WiFi mreži bez autentikacije - u redu za kućnu/uredsku
   mrežu, ne ostavljaj ovako pokrenuto na javnoj/nepouzdanoj mreži.
2. Pronađi lokalnu IP adresu računala:
   - Windows: `ipconfig` u CMD-u, traži "IPv4 Address" (npr. `192.168.1.50`)
   - Mac/Linux: `ifconfig` ili `ip addr`
3. Na telefonu (ista WiFi mreža) otvori Chrome i idi na `http://<IP-adresa-računala>:8010`
   (npr. `http://192.168.1.50:8010`).
4. Chrome izbornik (tri točke gore desno) → **"Dodaj na početni zaslon"** (Add to Home screen).
   Dobiješ ikonu na telefonu koja otvara dashboard u punom zaslonu, bez adresne trake preglednika.

**Važno ograničenje**: ovo je obično HTTP, ne HTTPS. Service worker (koji bi omogućio pravu
"instaliraj aplikaciju" ponudu i keširanje) treba HTTPS da bi radio - preglednici ne dopuštaju
service workere na nesigurnim izvorima osim `localhost`. Ručno "Dodaj na početni zaslon" iz
izbornika i dalje radi preko običnog HTTP-a i daje ti ikonu + prozor bez adresne trake, što za
ovaj slučaj (živi podaci, ne treba offline keširanje) sasvim pokriva potrebu. Ako jednom poželiš
pravu instalabilnost (auto-prompt, offline shell), trebao bi server staviti iza HTTPS-a
(samopotpisani certifikat + ručno povjerenje na telefonu, ili reverse proxy s pravim certifikatom)
- javi ako to želiš pa se dogradi.

## Kako je provjereno

Backtest engine je testiran tako da `baseline_2pct` na BTC/EUR, 2024-01-01 do 2026-11-21, daje
**točno** isti rezultat kao priloženi izvještaj (165 trgovina, 47 profitabilnih, 108,41 € završni
saldo, 79,11% maksimalni pad) — vidi `rezultat_testa.json` u izvorno priloženom paketu. Ovo
potvrđuje da čitanje podataka i troškovni model (0,1% slippage + 0,4% naknada po strani) rade
ispravno prije nego im se vjeruje za nove strategije. `equity_filtered` je dodatno provjeren
umetanjem sintetičkih S&P 500 podataka izravno u bazu (zaobilazeći mrežni poziv) kako bi se
potvrdilo da se aux podaci ispravno povlače i koriste u odluci te da nedostajući podaci bacaju
jasnu grešku umjesto tihog zanemarivanja filtra.

**Coinbase i Stooq integracije (javni feed, autenticirani pozivi, format naloga/CSV-a) NISU uživo
testirane** — ovo razvojno okruženje nema izlazni pristup internetu. Prije stvarnog korištenja:
1. Pokreni server negdje s normalnim internet pristupom.
2. Klikni "Testiraj vezu" u oba odjeljka (Wall Street i Coinbase) — ako jave grešku, popravak je
   izoliran u `app/coinbase_client.py` odnosno `app/equity_client.py` (endpoint, format odgovora,
   simboli poput `^spx`/`^dji`/`^ndq`).
3. Pokreni paper trading i prati barem nekoliko dana/tjedana prije nego vjeruješ signalima.

## Zaključan test metodologija - provjera protiv stručnog savjeta (ChatGPT, točka 3)

Korisnik je proslijedio savjet: zaključaj završni test prije podešavanja, izbaci primjere čiji
ciljni prozor ulazi u test razdoblje, izvrši po prvoj dostupnoj cijeni nakon odluke, usporedi s
buy&hold/gotovinom, ponovi s nepovoljnijim troškovima. Provjereno protiv postojećeg koda - VEĆINA
ovoga je već bila ugrađena prije ovog savjeta (iz ranijih ChatGPT-ovih neovisnih revizija), samo
nedovoljno istaknuto. Konkretno, po točkama:

- **"Izbaci primjere čiji ciljni prozor ulazi u test"** → već postoji: `app/ml/dataset.py`
  `walk_forward_folds(purge_seconds=...)`, pozvano iz `app/ml/train.py` s
  `purge_seconds = steps_ahead * interval_min * 60` za svaki horizont. Test blok u svakom foldu
  NIKAD ne sudjeluje u treningu/kalibraciji tog istog folda niti bilo kojeg ranijeg.
- **"Izvrši po prvoj dostupnoj cijeni nakon odluke"** → već postoji: `run_generic_backtest`
  donosi odluku na indeksu `i` (zatvorena svijeća `i`), a izvršava na `candles[i+1].open`
  (SLJEDEĆE otvaranje), nikad na cijeni svijeće na kojoj je odluka donesena.
- **"Usporedi s buy&hold i gotovinom"** → buy&hold je oduvijek postojao kao referentna strategija
  u "Usporedba strategija" (odjeljak 4); **novo u ovom commitu**: dodan eksplicitan red "Gotovina
  (bez trgovanja)" u istu tablicu/graf - ravna linija na polaznom iznosu, da se vidi "je li se
  uopće isplatilo nešto raditi" bez mentalnog računanja.
- **"Ponovi test s nepovoljnijim izvršenjem"** → već postoji: `run_cost_sensitivity` +
  `COST_SCENARIOS` (odjeljak 4, "Osjetljivost na naknade/slippage") - uključuje `pessimistic_illiquid`
  scenarij baš za ovu svrhu. Sad dodatno dopunjen maker/taker razlikom (vidi odjeljak iznad).
- **"Zaključaj završni test prije podešavanja parametara"** → za rule-based strategije,
  `app/optimizer.py` traži parametre ISKLJUČIVO na in-sample razdoblju, a out-of-sample provjera
  ide tek na top 5 kandidata NAKON što su već odabrani - out-of-sample razdoblje se nikad ne
  koristi za biranje. Za ML model nema odvojenog koraka "biranja hiperparametara" (fiksni su),
  pa se pitanje ne postavlja na isti način - svaki walk-forward test blok se koristi točno
  jednom, nikad za podešavanje.

**Što ostaje otvoreno**: ništa u kodu trenutno ne sprječava ČOVJEKA da ručno pogleda
out-of-sample/test brojke za VIŠE kombinacija nego što optimizator automatski vrati (top 5) i
naknadno "bira" na temelju toga - kod strukturno pomaže (ne vraća sve kombinacije automatski), ali
disciplina da se out-of-sample stvarno gleda samo jednom je i dalje na korisniku, ne (samo) na kodu.

## Ablacijski test (`app/ml/ablation.py`) - ChatGPT savjet, točka 1, djelomično izvediv odavde

Korisnik je tražio da se izmjeri koliko Wall Street i vijesti stvarno dodaju AI Prediction Engineu
- dobra hipoteza, vrijedna testiranja umjesto pretpostavljanja. Puna verzija (kripto → +Wall Street
→ +Wall Street+vijesti) NIJE izvediva iz ovog razvojnog okruženja:
- **Stooq (Wall Street)** - blokiran (anti-bot filter, uživo potvrđeno i za simbole za koje smo
  sigurni da su ispravni, vidi "Ograničenja koja treba znati").
- **CryptoPanic, Reddit, FRED (vijesti/sentiment)** - trebaju BESPLATNE, ali OSOBNE API ključeve
  koje samo korisnik može registrirati, nisu postavljeni u `.env` ovog okruženja.

**Što JEST testirano** (kao dokazana demonstracija metodologije, ne doslovno traženi izvori):
DeFiLlama TVL (Total Value Locked) kao proxy dodatni izvor - besplatan, bez ključa, duboka povijest
(3347 dana za ETH, 2080 za SOL). Dostupan SAMO za ETH/SOL (nema TVL koncepta za BTC/XRP), pa je
test ograničen na ta dva para - **ISTA populacija primjera u obje varijante** (ne različit broj
parova po varijanti, što bi usporedbu učinilo nepoštenom).

**Pošten rezultat** (24h horizont, walk-forward, isti purge/embargo kao `app/ml/train.py`):
- Baseline (samo cijena/tehnički): Brier score 0.53006 (bazna linija bez modela: 0.52361) - **ne
  prolazi validaciju** (model nije bolji od "ne znam ništa").
- +TVL (ista populacija primjera, dodan `tvl_roc7`): Brier score 0.53188 - **blago GORE od
  baselinea**, i dalje ne prolazi validaciju.
- **Zaključak**: dodavanje TVL-a ovdje NIJE pomoglo - naprotiv, blago je pogoršalo rezultat. Ovo je
  upravo vrsta nalaza koju ablacijski test treba otkriti (umjesto da se pretpostavi da "više
  podataka = bolje"), čak i kad je odgovor "ne pomaže".
- Pokreni `python3 -m app.ml.ablation` za ponovnu provjeru (ispisuje pune walk-forward metrike).

**Za PUNU verziju** (Wall Street + prave vijesti): pokreni isti kod na serveru gdje Stooq radi,
registriraj besplatne API ključeve (CryptoPanic, Reddit, FRED - svaki par minuta), sinkroniziraj
podatke preko postojećih dashboard sekcija, pa proširi `app/ml/macro_features.py` po istom obrascu
(`load_series` već rješava point-in-time ispravnost preko `available_date`) za Wall Street
povrat/`us_market_open` zastavicu i kombinirani sentiment skor.

## Stvarna ograničenja veličine naloga + simuliran dnevnik transakcija (ChatGPT savjet, točka 5, prilagođeno simulaciji)

Savjet je uključivao hrvatsku poreznu evidenciju za STVARNU kapitalnu dobit (12%, JOPPD) -
korisnik je odabrao prilagodbu simulaciji. Ono što je ugrađeno:

- **Stvarna ograničenja veličine naloga**: `get_product_constraints()` dohvaća Coinbaseov
  `min_market_funds` (minimalan iznos naloga u kotirajućoj valuti, npr. 1 USD) i `base_increment`
  (najmanji korak količine - npr. PEPE se mora kupovati u cijelim komadima, ne razlomljeno). Paper
  trading sad **odbija kupnju** ako je raspoloživa gotovina ispod minimuma (umjesto da tiho
  simulira nalog koji bi pravi Coinbase odbio), i zaokružuje kupljenu količinu NADOLJE na dopušteni
  korak - uživo potvrđeno (XRP min ~1€, PEPE base_increment=1 → kupljena količina je uvijek cijeli
  broj).
- **Simuliran dnevnik transakcija** - novi "Izvezi SVE trgovine u CSV" gumb (odjeljak 9): izvozi
  svaku trgovinu (preko svih paper trading runova) s rekonstruiranom količinom i naknadom po
  retku, za vježbu FIFO knjigovodstva. **Eksplicitno NIJE prava porezna evidencija** - nema stvarne
  kapitalne dobiti jer nema pravog novca; oznaka "SIMULACIJA" je u nazivu preuzete datoteke da se
  ne pomiješa sa stvarnim izvještajem.
- **Što NIJE napravljeno (namjerna granica opsega)**: "očekivani pomak, procijenjeni trošak i
  razlog za svaku odluku" bi zahtijevao da SVIH ~15 pravilima-vođenih strategija vraća strukturirano
  obrazloženje uz buy/sell/hold, ne samo odluku - prevelika izmjena za ovaj krug. AI Prediction
  Engine (odjeljak 1) to već radi (P(up)/P(down)/P(sideways), `reasons_for`/`reasons_against`) za
  ML dio sustava; isto za rule-based strategije ostaje otvoreno za budući rad.

## Pauza bota vs zatvaranje pozicije (ChatGPT savjet, točka 4, prilagođeno simulaciji)

Savjet je pretpostavljao PRAVO trgovanje (client_order_id idempotencija za prave naloge,
usklađivanje s Coinbaseovim računom nakon reconnecta) - korisnik je odabrao prilagodbu simulaciji
umjesto toga (vidi odjeljak "Isključivo savjetnik/simulator"). Ono što OSTAJE smisleno i bez pravog
novca:

- **Zastarjela kotacija**: Coinbase ponekad vrati uspješan HTTP odgovor, ali s davno zadnjom
  trgovinom (npr. par bez prometa, ili problem na Coinbaseovoj strani koji nije prava mrežna
  greška). `get_public_ticker()` sad vraća i `age_seconds` (koliko je star zadnji trgovinski
  podatak) - ako je stariji od 30 min, `paper_engine` PAUZIRA sve odluke tog ticka (uključujući
  maker nalog provjeru, ne samo nove ulaze) dok se kotacija ne osvježi, umjesto da odluči na
  sumnjivom podatku.
- **Dnevni limit gubitka** - NOVO polje pri pokretanju paper trading runa (odjeljak 9, opcionalno):
  prati equity (ne samo realizirane trgovine) naspram vrijednosti na početku kalendarskog dana
  (UTC). Ako gubitak probije zadani postotak, run **prisilno zatvara otvorenu poziciju** (taker
  prodaja po stvarnom bidu, odmah - ne čeka da strategija sama odluči) i blokira nove ulaze do
  idućeg dana, kad se referentna točka automatski resetira. Ovo je "zasebno pravilo s unaprijed
  definiranim uvjetom izlaza" točno kako je savjetovano.
- **Idempotencija bez client_order_id-a**: budući da nema pravih naloga, nema ni potrebe za
  idempotentnim ID-om kod ponovnog slanja - stanje "nalog čeka ispunjenje" (`pending_side` u bazi,
  ne u memoriji procesa) već sprječava dupli nalog na istu stranu čak i da server padne i restarta
  se nasred čekanja (`resume_running_on_startup()` čita stanje iz baze, ne gubi ga).
- **Usklađivanje s pravim Coinbase računom** - namjerno izostavljeno: simulacija nema pravi račun s
  kojim bi se trebala uskladiti, njeno stanje se UVIJEK rekonstruira iz vlastitih zabilježenih
  trgovina (`_replay_state`), pa "drift" naspram vanjskog sustava strukturno ne može nastati.

## Realniji troškovni model za uživo simulaciju (`app/costs.py`, `app/coinbase_client.get_public_ticker`)

Korisnik je proslijedio stručan savjet (ChatGPT) o troškovnom modelu: koristiti stvaran Coinbase
bid/ask umjesto jedne "slippage" pretpostavke, razlikovati maker/taker naknadu, i ne pretpostaviti
izvršenje samo zato što je cijena "dotaknuta" na svijeći.

- **Što je popravljeno**: `get_public_ticker()` sad dohvaća stvaran bid/ask s Coinbasea (ne samo
  zadnju cijenu trgovanja). Paper trading i auto-trader za TAKER izvršenje sad plaćaju stvarni
  ask (kupnja) / bid (prodaja), plus malen preostali slippage (0,05%) za kašnjenje odluka→izvršenje
  koje spread/dubina knjige još ne pokriva - umjesto stare pretpostavke "cijena ± 0,1%" koja nije
  znala stvaran trenutni spread.
- **Novo: maker/post-only način izvršenja** (izbor pri pokretanju paper trading runa, odjeljak 9):
  nalog se postavlja NA trenutni bid (kupnja) / ask (prodaja), ne prelazi spread. Svaki sljedeći
  tick (5 min) provjerava je li tržište stvarno došlo do te cijene - ako da, ispunjen je (jeftinija
  maker naknada, bez dodatnog slippagea); ako ne nakon 15 min (3 ticka), nalog ISTEKNE neispunjen i
  prilika se gubi (ne juri se za tržištem). Ovo izravno adresira "dodir cijene na svijeći sam po
  sebi ne potvrđuje izvršenje".
- **MAKER_FEE/TAKER_FEE su i dalje ORIJENTACIJSKI** (0,4%/0,6%) - Coinbase Advanced Trade ima razine
  po 30-dnevnom volumenu koje se mijenjaju, nisu uživo provjerene protiv tvog stvarnog računa (vidi
  coinbase.com/advanced-fees). Prije ozbiljnog korištenja provjeri svoj trenutni cjenik i po potrebi
  izmijeni konstante u `app/costs.py`.
- **Što NIJE popravljeno (strukturno ograničenje, ne nedostatak truda)**: HISTORIJSKI backtest
  (odjeljak 4, Optimizator) i dalje koristi staru fiksnu slippage pretpostavku na OHLC svijećama -
  povijesni bid/ask podaci (dubina knjige kroz vrijeme) se nikad nisu sakupljali, pa se ne mogu
  rekonstruirati unatrag. Realnije izvršenje je zato dostupno SAMO za uživo simulaciju (paper
  trading, auto-trader), ne za backtest na povijesnim podacima. Djelomična ispunjenja (dio naloga
  po jednoj cijeni, ostatak po drugoj) također nisu modelirana - maker nalog je sad ili potpuno
  ispunjen ili potpuno istekne, ne djelomično.

## Automatizirani paper trading (AI bira coin) (`app/auto_trader.py`, dashboard odjeljak 10)

Korisnik je tražio automatizirano trgovanje gdje aplikacija sama bira koji coin kupiti/prodati,
unutar ograničenog iznosa, više puta dnevno. To se izravno sudara s pravilom #2/#3 ispod (nikad
pravi nalozi, nikad Coinbase trgovački ključevi) - umjesto da se to pravilo zaobiđe ili ukine,
korisniku je eksplicitno ponuđen izbor između automatiziranog **paper** tradinga (bez pravog
novca), pravog automatiziranog tradinga uz jasno upozorenje o riziku, ili samo razgovora o opcijama.
**Korisnik je odabrao automatizirani paper trading** - ovo poglavlje opisuje upravo to, i samo to.

- **Odabir coina**: na svakoj granici horizont-perioda (svaki sat za `1h`, svaka 4 sata za `4h`),
  pozove se već postojeći AI Prediction Engine (odjeljak 1) za svaki par iz univerzuma (po
  defaultu korisnikov portfolio, `binance_history_client.PORTFOLIO_PAIRS`) i rangira kandidate za
  kupnju po AI Score-u, od najvišeg prema najnižem.
- **Samo validirani horizonti**: koristi se isključivo `1h` ili `4h` (vidi `data/models/metadata.json`
  - `validated` zastavica po horizontu, iz walk-forward provjere opisane u odjeljku "AI Prediction
  Engine"). `/api/auto-trader/start` odbija zahtjev (400) ako odabrani horizont trenutno nije
  validiran.
- **Sigurnosna provjera pri svakoj odluci**: `is_horizon_validated(horizon)` u `app/ml/engine.py`
  čita `metadata.json` svježe s diska (ne iz keša) prije svake odluke - ako naknadno ponovno
  treniranje makne validaciju za horizont dok je run već pokrenut, run se **automatski zaustavlja**
  umjesto da nastavi "trgovati" na modelu koji više ne prolazi provjeru.
- **Ograničenje ulaganja**: `max_position_pct` (default 20%) ograničava koliko se od **početnog**
  budžeta smije uložiti u jedan coin odjednom; broj istovremeno otvorenih pozicija je ograničen na
  `1 / max_position_pct` (npr. 20% → najviše 5 pozicija odjednom), pa je cijeli virtualni budžet
  uvijek gornja granica izloženosti, nikad više.
- **Jedna odluka po horizont-periodu**: provjera cijene/equity-a ide svakih 5 minuta (za glatku
  krivulju), ali stvarna odluka kupi/prodaj se donosi samo jednom po satu/4h (ovisno o horizontu) -
  sprječava pretjerano trgovanje unutar iste svijeće.
- **Izlasci prije ulaska**: na svakoj odluci se prvo provjeravaju postojeće pozicije (prodaja ako
  AI Prediction Engine za taj par sada javlja SELL/STRONG SELL), pa tek onda eventualni novi ulasci
  u najbolje rangirane BUY/STRONG BUY kandidate koji nisu već u portfelju.
- **Potpuni trag**: svaka kupnja/prodaja upisuje se u `auto_trader_trade` zajedno s AI Score-om i
  kategorijom odluke u trenutku trgovanja (za reviziju unatrag) - vidi "Detalji" u dashboard
  sekciji 10.
- **I OVO JE SIMULACIJA**: cijene su stvarne, žive (javni Coinbase feed), ali novac je virtualan -
  isti FEE/slippage model kao backtest i paper trading (odjeljak 9), bez ikakvog Coinbase
  trgovačkog ključa ili pristupa računu. Nema koda koji bi ovo mogao pretvoriti u pravi nalog bez
  da se prvo ponovno napiše `live_engine.py` (uklonjen, vidi pravilo ispod) i autenticirani
  Coinbase klijent.

### Swing način rada (`trade_mode="swing"`)

Korisnik je tražio da auto-trader ima i "swing trade" opciju. Dvije stvari je bitno razlučiti prije
nego se objasni što je napravljeno:

- **24h/7d horizonti i dalje NISU validirani** (provjereno uživo prije ovog dodatka: 24h Brier
  score 0.51349 nasuprot bazne linije 0.51368 - ispod praga od 2% relativnog poboljšanja koji
  `beats_baseline()` traži; 7d jasno gori, 0.55088 nasuprot 0.54369). Swing način rada NE koristi
  te horizonte - i dalje radi isključivo na `1h`/`4h` (jedini validirani), isto kao i scalp način.
- Umjesto duljeg horizonta, "swing" ovdje znači **drugačija disciplina držanja pozicije** na ISTOM
  validiranom 1h/4h signalu: ne izlazi čim AI Score na trenutak padne na SELL/STRONG SELL (kao
  scalp), nego drži kroz manje oscilacije dok ne prođe zadano `min_hold_periods` horizont-perioda
  OD ULASKA.

Pravila izlaska u swing načinu (provjeravaju se svaki put kad dođe nova horizont-periodna odluka):
1. **Stop-loss djeluje UVIJEK**, čak i prije isteka `min_hold_periods` - sigurnosni izlaz se ne
   odgađa zbog "drži kroz oscilacije" discipline.
2. Nakon proteka `min_hold_periods`: izlazi na dosegnut **profit cilj** (`take_profit_pct`) ILI na
   AI **SELL/STRONG SELL** signal, što prije nastupi.
3. Prije isteka `min_hold_periods` (i bez probijenog stop-lossa): **ništa ne radi**, čak i da AI
   Score padne na SELL - to je upravo razlika naspram scalp načina.

**POŠTENO OGRANIČENJE**: swing način rada NIJE backtestiran i ne postoji plan da bude - AI
Prediction Engine računa predikciju UŽIVO (poziva se na trenutnu Coinbase cijenu), nema povijesnog
"replaya" predikcija kroz prošlost kao što rule-based strategije imaju u `app/backtest.py`.
Backtestiranje bi zahtijevalo ili spremanje predikcija svaki sat unaprijed (još ne postoji) ili
ponovno treniranje modela na "zamrznutom" skupu podataka za svaku točku u prošlosti (skupo,
nije napravljeno). Dok se to ne napravi, swing način rada je **isto toliko neprovjeren kao i sam
auto-trader prije njega** - promatraj ga, ne vjeruj mu unaprijed. Zadane vrijednosti u dashboardu
(`min_hold_periods=6`, bez profit cilja, stop-loss prazan ali preporučen) su razumne pretpostavke,
ne rezultat ikakve optimizacije.

## Whale mirror (`app/whale_mirror.py`, `app/etherscan_client.py`, dashboard odjeljak 11)

Korisnik je tražio "praćenje kitova" i/ili "kopiranje javnih portfelja" - dvije ideje koje su prvo
istražene i odbačene u izvornom obliku, a onda izgrađene u jedinom obliku koji je stvarno poštena i
izvediva verzija:

- **"Kopiraj anonimnog trgovca s burze" NIJE izvedivo na legitiman način.** Binance/Bybit/OKX ne
  objavljuju tuđe pozicije kao pravi, dokumentirani API - njihove "leaderboard" stranice su
  neslužbeni, interni pozivi koje njihov JavaScript radi, bez ugovora o stabilnosti. Uživo testirano
  (25.11.2026.): direktno pogađanje tih putanja vraća 404 (putanje se mijenjaju bez najave), a
  pokušaj da se stvarna putanja nađe inspekcijom njihove stranice je OVO razvojno okruženje samo
  blokiralo kao neovlašteni pristup - ispravna zaštita, ne slučajnost. Čak i kad bi se put našao, ne
  postoji besplatna povijest tuđih pozicija za pravi backtest - samo trenutno stanje.
- **Pravi, stabilan, dokumentiran i besplatan put**: javni on-chain podaci. Stanje ETH novčanika je
  PO DEFINICIJI javan podatak u lančanom registru - nema tu ničije privatnosti za narušiti, za
  razliku od pokušaja čitanja tuđih burzovnih pozicija. Etherscan nudi besplatan, dokumentiran,
  stabilan API (v2, `chainid` parametar) - uživo testirano s korisnikovim besplatnim ključem,
  radi normalno iz ovog sandboxa (za razliku od Binance/CoinGecko/FRED/Reddit koji su odavde
  blokirani).

### Kako radi

Svakih 10 minuta (`POLL_INTERVAL_SECONDS` u `app/whale_mirror.py`) provjeri trenutno ETH stanje
praćene javne adrese i usporedi sa zadnje zabilježenim stanjem:

- stanje poraslo za barem `threshold_pct` (npr. 3%) i NISMO u poziciji -> **kupi** (zrcali
  "akumulaciju")
- stanje palo za barem `threshold_pct` i JESMO u poziciji -> **prodaj** (zrcali "distribuciju")
- inače ništa

Svaka trgovina je sve-ili-ništa (cijela gotovina/pozicija) - kopira se SMJER, ne iznos (praćeni
novčanik je reda veličine $10k-$1M+, naš simulirani bot $100-1000 - proporcionalno kopiranje iznosa
ne bi imalo smisla). Zadana adresa u dashboardu je Ethereum Foundationina javna adresa
(`0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe`, javno objavljena u njihovim izvještajima
transparentnosti) - bilo koja druga javna ETH adresa može se unijeti ručno.

### Pošteno ograničenje - OVO JE HEURISTIKA, NE PROVJEREN SIGNAL

Balans adrese se mijenja iz mnogo razloga koji nemaju veze s "trgovanjem": naknade za obične
transakcije (gas), premještanje sredstava između vlastitih novčanika, staking, kupnja NFT-ova...
Etherscan ne daje (barem ne na besplatnom tieru) razlog ZAŠTO se balans promijenio, samo da jest.
`threshold_pct` filtrira sitan šum (gas naknade su obično mali dio balansa), ali ne može razlikovati
"kupio je ETH jer vjeruje da će rasti" od "premjestio je ETH u drugi svoj novčanik". Ovo je proxy za
whale AKTIVNOST, ne dokazan trgovački signal - tretiraj ga kao takvog.

**NEMA POVIJESNOG BACKTESTA.** Etherscan daje SAMO trenutno stanje i popis transakcija - ne postoji
besplatan način da se sazna "kakvo je bilo stanje ove adrese prije 30 dana" bez ručnog prolaska kroz
svaku transakciju unatrag (skupo, nije napravljeno). Ovo je čisto uživo praćenje od trenutka
pokretanja nadalje, isto neprovjereno kao i auto-trader kad je prvi put pokrenut - promatraj ga, ne
vjeruj mu unaprijed.

### Postavljanje

Treba besplatan Etherscan API ključ (`etherscan.io/apis`) u `.env` (`ETHERSCAN_API_KEY`). Bez njega
ovaj dio dashboarda jednostavno ne radi, ostatak aplikacije radi normalno. Napomena: ovaj projekt do
sada NIJE automatski učitavao `.env` (nedostajao je `python-dotenv` + `load_dotenv()` poziv u
`app/config.py` - popravljeno ovom prilikom, pogađa SVE postojeće `.env` ključeve, ne samo
Etherscan).

## Stepenice (`app/strategies/stair_step_swing.py`) - pošten nalaz

Korisnik je tražio bota koji "lovi stepenice": u uzlaznom trendu cijena malo raste pa malo padne pa
opet raste - ideja je kupiti ta mala povlačenja prije odskoka i prodati na lokalnom vrhu, više puta
dnevno, i dalje isključivo u simulaciji (bez pravog novca). Da bi se to uopće moglo testirati, Paper
trading (odjeljak 9) je proširen da radi i na **satnim svijećama** (ne samo dnevnim kao prije) -
izbor intervala je sad dio obrasca za pokretanje runa.

Strategija: u širem trendu (zatvaranje iznad duge SMA) kupuje kad cijena dotakne/padne ispod donje
Bollingerove vrpce (lokalno povlačenje), a prodaje na: dosegnut profit cilj, dodir gornje vrpce
(lokalni vrh), stop-loss, ili slom šireg trenda.

**Pošten rezultat testiranja (grid pretraga 72 kombinacije parametara, BTC/USDT satne svijeće,
in-sample 2023-11 do 2025-11, out-of-sample 2025-11 do 2026-11-22):**
- Parametri dovoljno osjetljivi da bi stvarno trgovali "više puta dnevno" (uski Bollingerove vrpce,
  `bb_std=1.5`) **gube katastrofalno** - do 94% početnog iznosa. Razlog: uzorak koji djeluje
  bezazleno na oku (mali zig-zag) statistički ne razlikuje pravo povlačenje od početka pravog pada -
  uski filter hvata obje situacije podjednako, a gubici na pravim padovima nadjačaju dobitke na
  pravim povlačenjima.
- Najbolja pronađena kombinacija (širi filter, `bb_std=2.5`, vidi `DEFAULT_PARAMS` u kodu) gubi
  **blago na OBA razdoblja** (~8-12% od 1000€ polazišta), uz samo 5-16 trgovina u ~2 godine - rijetko,
  ne "više puta dnevno" kako je bila zamisao. Naknade (0,4%) + slippage (0,1%) po strani (~1%
  round-trip) jedu većinu male prednosti koju bi ovaj pristup inače mogao imati.
- **Zaključak**: ovaj točan pristup (Bollingerove vrpce + SMA trend filter na satnim BTC/USDT
  podacima) **nema dokazanu prednost** nakon troškova. Uključen je u aplikaciju kao alat za dalje
  istraživanje (probaj druge parove, kraće/duže periode, druge indikatore poput RSI/Stochastic RSI
  umjesto Bollingerovih vrpci) - ne kao gotova preporuka za korištenje.
- Dashboard "Optimizator" (odjeljak 7) namjerno NE nudi ovu strategiju u padajućem izborniku zadanih
  mreža parametara - radi samo na dnevnim svijećama, a ova strategija je dizajnirana za satne, pa bi
  tiho davao besmislene rezultate. Daljnje testiranje treba raditi ručno (`app/optimizer.optimize`
  pozvan izravno s `interval_min=60`) dok se Optimizator ne proširi na proizvoljan interval.

## Stepenice v2 (`app/strategies/stair_step_stochrsi.py`) - pošten nalaz (GORI od v1)

Drugi, drugačiji mehanizam za isti cilj, na korisnikov zahtjev nakon v1: umjesto dodira Bollingerove
vrpce, Stochastic RSI **presjek** preko granice prenisprodanosti/prekupljenosti (hvata trenutak
zaokreta, ne cijelo razdoblje niske vrijednosti) + SMA trend filter + stop-loss.

**Pošten rezultat testiranja:**
- Prvi test (4 odvojena povijesna razdoblja × 4 para, zadani parametri): **gubi 65-90% u SVAKOJ**
  od 16 kombinacija razdoblje/par, bez iznimke. 130-180 trgovina po razdoblju (svaka 2-5 dana) -
  puno češće nego v1, i puno gore.
- Grid pretraga 81 kombinacije (BTC/USDT satno, in-sample 2023-11 do 2025-05, out-of-sample
  2025-05 do 2026-11): **najbolja pronađena kombinacija gubi ~94% in-sample i ~90% out-of-sample.**
  Nijedna od 81 testiranih kombinacija nije bila ni blizu profitabilnosti.
- **Zaključak: ovaj pristup je GORI od v1 (Bollingerove vrpce), ne bolji.** Presjek preko granice
  okida se prečesto (puno kraći "signal" traje nego dodir vrpce), a svaka dodatna trgovina znači
  još ~1% round-trip troška - uz 130-290 trgovina po razdoblju to brzo pojede sav kapital. Ostavljen
  je u kodu kao dokumentiran negativan nalaz (uči se i iz onoga što NE radi), ne kao preporuka -
  **ne koristi ovu strategiju.**
- **Širi zaključak nakon dva neovisna pokušaja**: problem nije (samo) izbor indikatora nego
  temeljni kompromis - svaki mehanizam dovoljno osjetljiv da stvarno hvata "stepenice" više puta
  dnevno/tjedno nužno hvata i prave preokrete, a trošak svake dodatne trgovine (~1% round-trip)
  brzo nadjača male dobitke na pravim povlačenjima. Čista tehnička analiza na satnim
  kripto-podacima (barem BTC/ETH/SOL/XRP, ova dva mehanizma) **ne pokazuje dokazanu prednost**
  nakon realnih troškova.

## Isključivo savjetnik/simulator (KriptoMVP 4.4 nepromjenjiva pravila)

Aplikacija **nikada ne izvršava prave naloge** i ne traži Coinbase trgovačke (autenticirane) API
ključeve niti pristup računu/novčaniku - ta mogućnost (`app/live_engine.py`, autenticirani dio
`app/coinbase_client.py`, `/api/live/*` rute, dashboard sekcija "Live trgovanje") je namjerno
potpuno uklonjena iz koda, ne samo isključena zastavicom - vidi git povijest ako ti treba za
referencu. Koristi se isključivo javni, read-only Coinbase cjenovni feed (bez ključa), za paper
trading (ručni, odjeljak 9, i automatizirani, odjeljak 10) i backtest. "Automatizirano" u
odjeljku 10 znači autonomna ODLUKA unutar simulacije, ne pravi nalog - vidi poglavlje iznad.

## Provjera savjeta o upravljanju rizikom (korisnik je podijelio opći "Copilot" savjet o trgovanju)

Korisnik je podijelio generički sažetak savjeta o trgovanju kriptovalutama (rizik 0,5-2% po
trgovini, trend-following, price action, breakout, mean reversion, momentum, "Smart Money
Concepts") i tražio da se to poštenо provjeri i primijeni kao "najbolji svjetski tim". Evo
poštene procjene, razdvojeno na ono što je utemeljeno i što nije:

**Utemeljeno, i VEĆ POKRIVENO u ovom projektu:**
- Trend following (EMA20/50/200) → `ema_trend`, `trend_guard`, `vol_guarded_trend`, `dual_momentum`
- Breakout → `donchian_breakout` (potvrđeno: puno lažnih breakouta, visok max pad u našim testovima - točno kako savjet upozorava)
- Mean reversion (RSI, Bollinger) → `rsi_meanrev`, `stair_step_stochrsi` - **ALI naši stvarni testovi
  pokazuju da su ovo najgore strategije koje imamo** (365-dnevni test: `rsi_meanrev` -45%, `stair_step_stochrsi`
  -87%). Generički savjet ne kaže je li ovo stvarno profitabilno za kripto - naš podatak kaže NE.
- Momentum (volumen, OBV, MACD) → `technical_composite`, `dual_momentum`

**Utemeljeno, a NEDOSTAJALO nam je — popravljeno ovom prilikom:**
- **Stop-loss i veličina pozicije prema riziku.** Niti jedna od 16 strategija do sad nije imala
  TVRDI stop-loss - izlaz je bio isključivo na signal strategije. Ovo je stvarno najvažnija,
  najbolje utemeljena stavka iz cijelog savjeta (standardna teorija upravljanja pozicijama, npr.
  "fixed fractional position sizing" - Van Tharp i srodna literatura, ne nešto specifično za kripto).
  Dodano u `app/backtest.py` (`run_generic_backtest`, parametri `stop_loss_pct`/`risk_pct`) i
  dashboardu (odjeljak 3, "Prilagodi parametre jedne strategije").

  **Pošteno testirano na istom 365-dnevnom/4-para skupu** (ema_trend, vol_guarded_trend,
  trend_guard) - rezultat NIJE jednoznačno "sve je bolje s rizik managementom":
  - Sam tvrdi stop-loss (bez promjene veličine pozicije) **blago POGORŠAVA sirov povrat** u ovom
    uzorku (npr. vol_guarded_trend: $106,44 → $99,99-104,56 ovisno o širini stopa) - razlog je
    whipsaw: stop istrese poziciju, cijena se vrati, strategija ponovno uđe, plati se dvostruka
    naknada. Ovo je POŠTEN nalaz koji generički savjet ne spominje - stop-loss nije besplatan.
  - Veličina pozicije prema riziku (npr. risk 1-2% uz stop 8%) **dramatično smanjuje max pad**
    (s 11-18% na 2-5%) **ALI proporcionalno smanjuje i povrat** (npr. ema_trend: +10,6% → +1-2%)
    - to je matematička nužnost, ne otkriće: manja pozicija = manji zamah u oba smjera. Nije
      "besplatan ručak", pravi kompromis rizik/povrat.
  - **Uzorak je malen** (5-25 trgovina) - ista zamka kao i prije, ne vjeruj ovom testu previše u
    bilo kojem smjeru dok se ne nakupi više podataka iz uživo simulacije.

**NIJE utemeljeno, NEĆE biti implementirano:**
- **Smart Money Concepts (SMC/ICT)** - order blocks, Fair Value Gap, liquidity grab, BOS/CHOCH.
  Problem nije da je "pogrešno", nego da pojmovi NISU precizno, jednoznačno mehanički definirani u
  zajednici koja ih koristi - svaki trader drugačije označava "order block" na grafu. Kodirati ovo
  kao da je jedna, dogovorena metoda bilo bi suprotno temeljnom pravilu ovog projekta (nikad ne
  predstavljaj heuristiku kao više nego što jest). Nema ni ozbiljne recenzirane akademske potvrde
  da "institucije love lov na stop-loss naloge" ima mjerljivu prediktivnu vrijednost iznad onoga
  što već hvataju jednostavniji indikatori koje imamo.
- **Pojedinačni svijećni obrasci** (Pin Bar, Engulfing, Inside Bar) kao samostalan signal - slaba
  dokazana prednost u modernim likvidnim (pogotovo arbitriranim) tržištima prema akademskoj
  literaturi o tehničkoj analizi; mogu biti dio konteksta, ne pouzdan samostalan okidač.

**VWAP** (spomenut u savjetu kao jedan od ključnih indikatora) trenutno nemamo u `app/indicators.py`
- nije dodano ovom prilikom (nizak prioritet, prvenstveno koristnije za kvalitetu izvršenja unutar
  dana nego kao samostalan dnevni signal), ali ostaje kandidat za budućnost.

## Konkretan "bot pravilnik" (korisnik je podijelio detaljan "Copilot" skup pravila) - testirano

Korisnik je podijelio puno konkretniji nacrt bota (4h trend/15m ulaz, EMA50/200, RSI pullback zona
40-60, volumen filter, ATR stop ×1,5, R:R 1:3, rizik 0,5%/trgovina, max 3 uzastopna gubitka, max 3%
dnevni pad, zabrana Martingalea/mijenjanja stopa/trgovanja oko FED-CPI objava) i tražio da se to
stvarno izgradi i provjeri.

**Što NIJE izvedivo i zašto:**
- **SHORT strana** - cijeli projekt je namjerno spot long-only, bez poluge/shortanja (vidi
  "Ograničenja koja treba znati"). Testirana je SAMO long strana.
- **Zabrana trgovanja oko FED/CPI objava** - trebao bi ekonomski kalendar s točnim datumima objava
  (FRED daje same vrijednosti podataka, ne raspored budućih objava) - nemamo takav izvor, nije
  dodano. Ostale zabrane (Martingale, povećanje poluge nakon gubitka, micanje stopa) su već
  automatski poštovane jer ih sustav strukturno ne dopušta.

**Što JEST izgrađeno i pošteno testirano** (`app/backtest.py` prošireno):
- `atr_stop_mult`/`atr_period`: stop = entry - ATR×multiplikator (umjesto fiksnog %), računat
  jednom na ulasku iz ograničenog nedavnog prozora svijeća (ne cijela rastuća povijest - izbjegava
  poznati O(n²) problem).
- `take_profit_r_multiple`: izlaz kad next_candle.high dosegne entry + (entry-stop)×multiplikator.
- `max_consecutive_losses`/`max_daily_drawdown_pct`: pauzira NOVE ulaske (postojeće pozicije i
  dalje poštuju stop/TP) do sljedećeg kalendarskog dana (UTC).
- Rezultat sad uključuje `profit_factor` i `avg_r_multiple` - točno mjere koje korisnikov savjet
  traži da se prate.

**VAŽAN NALAZ (pravi bug uhvaćen prije isporuke, ne spekulacija)**: prva verzija veličine pozicije
prema riziku (`risk_pct / stop_distance_pct`) je **ignorirala trošak naknade+slippagea** pri
računanju koliko uložiti. Na 15-minutnim BTC/ETH svijećama, ATR×1,5 stop je uzak (0,3-0,9% cijene) -
MANJI ili usporediv s cijenom punog kruga trgovine (~1% - 2×0,4% naknada + 2×0,1% slippage). Sustav
je zato ulagao OGROMAN dio kapitala (do 100%) baš kad je stop uzak (da "sačuva" 0,5% rizika), a
naknada se naplaćuje na CIJELI uloženi iznos bez obzira na širinu stopa - stvaran gubitak po
pogođenom stopu je ispao 2-3× veći od namjeravanog (prosj. R -3,67 umjesto očekivanog ~-1). PRIJE
isporuke ovo je ispravljeno: nazivnik formule sad uključuje procijenjen trošak punog kruga
(`2×(FEE+SLIPPAGE)`) - `fraction = risk_pct / (stop_distance_pct + trošak_punog_kruga)`. Nakon
popravka, prosj. R po trgovini je ~-0,7 do -0,8, kako i treba biti za stop koji se stvarno pogodi.
Ovaj popravak utječe na SVE buduće korištenje `risk_pct` (ne samo ovaj bot), ali je neznatan za
široke dnevne stopove (5-15%) iz prijašnjeg odjeljka - brojevi ondje ostaju praktički isti.

**Pošten rezultat nakon popravka** (90 dana, 15-min svijeće, $1000 start, ograničeno dostupnom
5-min poviješću od ~113 dana - kraći uzorak nego inače):

| Par | Trgovina | Win rate | Profit factor | Prosj. R | Završni saldo | Buy&hold |
|---|---|---|---|---|---|---|
| BTC/USDT | 62 (50 stop, 11 TP) | 6,5% | 0,016 | -0,76 | $789 | $767 |
| ETH/USDT | 57 (44 stop, 13 TP) | 19,3% | 0,083 | -0,67 | $827 | $677 |

Korisnikov VLASTITI savjet kaže da je cilj win rate 40-60% i profit factor >1,5 - ovaj konkretan
nacrt, OVAKO operacionaliziran, promašuje oba cilja daleko (win rate 6,5-19,3%, profit factor
0,02-0,08). Najvjerojatniji razlog: ATR×1,5 stop na 15-minutnim svijećama (0,3-0,9% cijene) je
preuzak za normalan šum BTC/ETH na tom vremenskom okviru - 77-81% trgovina završava na stop-lossu,
što upućuje da stop puca na obično komešanje, ne na stvaran obrat trenda. Ni ovaj nalaz ne treba
uzeti kao konačan - korisnikov vlastiti savjet kaže da se strategija smatra testiranom tek nakon
500-1000 trgovina, a ovdje ih imamo 57-62 (iako je profit factor toliko loš, 0,02-0,08, da je teško
zamisliti da bi se preokrenuo s više podataka).

## Kako analizirati rezultate dugoročne uživo simulacije

Korisnik je pokrenuo paralelno niz paper trading / auto-trader / whale-mirror runova (25.11.2026.)
da se vidi što stvarno radi kroz tjedne/mjesece. Plan analize, da se izbjegne isti problem kao kod
backtesta (samoobmana, biranje "pobjednika" prerano):

1. **Pusti da prođe dovoljno vremena prije bilo kakvog zaključka.** Dnevne strategije trebaju
   barem par tjedana da nakupe desetak+ trgovina (manje od toga = šum, ne signal - vidi "365-dnevni
   test rangiranja" iznad gdje je upravo ovo bio problem s `ema_trend`). 1h/4h auto-trader i whale
   mirror mogu pokazati nešto ranije jer donose odluke češće, ali i dalje treba barem nekoliko
   tjedana za bilo kakav pouzdan zaključak.
2. **Izvoz podataka**: svaki od tri sustava (paper trading, auto-trader, whale mirror) sad ima CSV
   izvoz svih trgovina (gumb "Izvezi SVE trgovine u CSV" u odgovarajućem odjeljku dashboarda, ili
   `/api/{paper,auto-trader,whale-mirror}/export-csv`). Pošto ja (Claude) nemam daljinski pristup
   korisnikovom serveru, analiza se radi tako da korisnik izveze CSV-ove i podijeli ih (ili
   screenshot sažetka s dashboarda) kad dođe vrijeme za pregled.
3. **Mjerila, ista disciplina kao kod backtesta**: konačni saldo NASUPROT buy&hold za isto
   razdoblje (ne apsolutni broj), broj trgovina (premalo = ne vjeruj rezultatu bez obzira je li
   dobar ili loš), max pad, i POŠTENO gledanje svih runova - uključujući one koji gube, ne samo
   "pobjednike". Isto pravilo kao uvijek: curve-fitting/biranje najboljeg nakon činjenice se ne
   računa kao dokaz.
4. **Nakon dovoljno podataka**: usporedi sve runove jedni s drugima (isti format kao "Koja
   strategija je stvarno najbolja" test), zadrži ono što pokaže dosljednu prednost, ugasi ostalo -
   ne nastavljaj raditi sve paralelno unedogled.

## Portfelj trend strategija (`app/portfolio_backtest.py`, dashboard odjeljak 12)

Odgovor na pitanje "kako to rade vrhunske firme": umjesto traženja JEDNE pobjedničke strategije na
JEDNOM coinu, profesionalni trend fondovi (CTA / managed futures, "time-series momentum") drže
**portfelj** - više tržišta, više signala, veličina pozicije prema riziku. Ovo je ta ideja,
iskreno testirana na našim podacima.

### Kako radi

1. Tri trend strategije koje su u ranijem 365-dnevnom testu rangiranja bile najbolje (`ema_trend`,
   `trend_guard`, `vol_guarded_trend`), **sa zadanim parametrima, bez ikakvog štimanja**, svaka
   vodi svoje virtualno stanje (u poziciji / van) na svakom coinu.
2. Signal coina = udio strategija koje su "unutra" (0, 1/3, 2/3 ili 1) - ansambl, ne jedan glas.
3. Rizik se dijeli prema **inverznoj volatilnosti** (30-dnevna realizirana): SOL dobije manju
   poziciju od BTC-a jer je divljiji, pa svaki coin nosi sličan rizik.
4. Opcionalno ciljanje volatilnosti portfelja (`target_vol`) - procjena pretpostavlja POTPUNU
   korelaciju coinova (konzervativno).
5. Bez poluge, ostatak u gotovini. Odluka nakon zatvaranja dana, izvršenje na otvaranju sljedećeg,
   naknada 0,4% + slippage 0,1% po strani, kapital mjeren kao likvidacijska vrijednost.
6. Rebalans samo kad se signal promijeni ili se težina udvostruči/prepolovi (`rebalance_drift=1.0`).

### Rezultati ($1000, BTC/ETH/SOL/XRP, dnevne Binance svijeće)

**Najpošteniji prozor: 2021-04 → 2025-11.** Ove tri strategije su izabrane na zadnjih 365 dana
(2025-11 → 2026-11), pa je prozor koji ne uključuje tu godinu "kvazi out-of-sample" - podaci koji
NISU utjecali na izbor.

| 2021-04 → 2025-11 | Završno | CAGR | Volatilnost | Sharpe | Max pad |
|---|---|---|---|---|---|
| Buy & hold, jednake težine | $3206 | 28,5% | 83,6% | 0,71 | **89,3%** |
| **Portfelj** (bez target_vol) | $3654 | 32,2% | 33,7% | **0,98** | 37,7% |
| Portfelj, target_vol 50% | $3030 | 27,0% | 29,7% | 0,94 | 34,5% |
| Portfelj, target_vol 30% | $2375 | 20,5% | 23,2% | 0,91 | 28,3% |
| 12 pojedinačnih (strategija × coin), MEDIJAN | - | 19,1% | - | 0,62 | 61,9% |

Cijelo razdoblje 2021-04 → 2026-11 (uključuje godinu izbora, pa je blago optimistično): portfelj
$3976, Sharpe 0,92, max pad 37,7% naspram buy&hold $1774, Sharpe 0,52, max pad 89,3%.

Po godinama (portfelj bez target_vol / buy&hold): 2021 +117% / +220%, **2022 −17% / −84%**,
2023 +29% / +309%, 2024 +58% / +103%, 2025 +0,1% / −24%, 2026 (do 22.11.) +9% / −44%.

### Što to znači - iskreno

- **Glavna korist nije veći povrat, nego preživljavanje.** U 2022. buy&hold je izgubio 84%, portfelj
  17%. Iz −84% treba +525% da se vratiš na nulu - zato portfelj na kraju završi iznad buy&holda
  iako u svakoj bikovskoj godini (2021, 2023, 2024) jako zaostaje.
- **Portfelj je bolji od tipične pojedinačne strategije** (medijan Sharpe 0,62, max pad 62%) - ali
  NIJE bolji od najbolje pojedinačne (ema_trend na SOL-u, Sharpe 1,11). To je očekivano i u redu:
  najbolju pojedinačnu znaš tek NAKNADNO, portfelj ne traži da pogodiš unaprijed.
- **Duge mrtve faze**: 2025. gotovo nula. Prosječna izloženost samo ~35% (ostatak gotovina).
  Trend sustavi tako izgledaju - dugo ništa, pa velik trend.
- Sharpe ~0,9-1,0 je u rangu onoga što stvarni CTA fondovi dugoročno postižu. Brojevi koji obećavaju
  puno više od toga gotovo su uvijek pretjerano optimizirani.
- Troškovi: 516 trgovina u 4,6 godina, naknade+slippage $744 (~6,5% prosječnog kapitala
  godišnje, promet ~13× godišnje) - uračunato u sve gornje brojke. To je velik trošak; uz niže
  naknade (veći Coinbase volumen ili limit nalozi) rezultat bi bio primjetno bolji.

### Ograničenja

- Samo 4 velika coina, i jako su korelirani (u padovima padaju zajedno) - stvarni CTA fondovi
  diverzificiraju preko desetaka nepovezanih tržišta (obveznice, valute, sirovine). Ovdje je
  diverzifikacija ograničena. Dodavanje još altcoina pomaže manje nego što zvuči.
- Strategije su izabrane na podacima iz 2025-26; čak i "kvazi out-of-sample" prozor nije pravi
  budući test - pravi test je tek uživo trgovanje od danas nadalje (paper trading).
- `rebalance_drift` je testiran na 4 vrijednosti (0,25/0,5/1,0/samo-signal); razlike su male
  (Sharpe 0,94-0,98), izabrano 1,0 jer manje trgovanja, ne jer je "pobijedio".
- Long-only spot, bez shortanja - u medvjeđem tržištu najbolje što portfelj može je biti u gotovini.

### Zašto ne SVE strategije odjednom? (testirano na korisnikovo pitanje)

Isti portfeljni engine, isti podaci ($1000, BTC/ETH/SOL/XRP). Testirano je 12 strategija kojima
treba samo cijena; 4 makro/derivatne strategije trebaju podatke kojih nema za cijelo razdoblje.
Dashboard odjeljak 12 sad ima izbor "Strategije" da se ovo može ponoviti.

| 2021-04 → 2025-11 (pošteni prozor) | Završno | Sharpe | Max pad | 2022 | Trgovina |
|---|---|---|---|---|---|
| Buy & hold | $3206 | 0,71 | 89,3% | −84% | - |
| **Naše 3 trend** | $3654 | **0,98** | 37,7% | −17% | 516 |
| **Svih 12 cjenovnih** | $3189 | 0,92 | 40,5% | −27% | 1816 |
| Svih 8 trend | $2913 | 0,90 | 38,3% | −18% | 1886 |
| Samo 4 kontra/swing | $4515 | 0,89 | 61,5% | −50% | 225 |

Na cijelom razdoblju do 2026-11 razlika je veća (naše 3: Sharpe 0,92; svih 12: 0,73), ali taj
prozor uključuje godinu na kojoj su naše 3 izabrane, pa je ta usporedba pristrana U NAŠU KORIST.

Zaključci:
- **Kombinacija svih nije loša ideja - radi.** Svih 12 bez ikakvog biranja i dalje jasno pobjeđuje
  buy&hold po riziku (Sharpe 0,92 naspram 0,71, pad 40% naspram 89%). Na poštenom prozoru je
  razlika prema "naše 3" mala (0,98 naspram 0,92) i dio te prednosti je vjerojatno upravo
  naknadno biranje.
- **Zašto ipak lošije:** 4 kontra/swing strategije (`rsi_meanrev`, `dip_buy_volume`,
  `stair_step_*`) su na DNEVNIM podacima uglavnom "kupi i drži" (izloženost 74-99%, neke samo 4
  trgovine u 4,6 godina). Kad se umiješaju, vraćaju upravo rizik pada koji trend sustav izbjegava
  (2022: −27% umjesto −17%). Trend i "kupi pad" su suprotne filozofije - djelomično se poništavaju.
- `dual_momentum` sam po sebi je loš (1395 trgovina, Sharpe 0,10) i razvodnjava ansambl.
- **Više strategija ≠ više diverzifikacije.** Svih 12 gleda istu cijenu istih 4 coina, pa su
  jako međusobno korelirane. Prava diverzifikacija dolazi od RAZLIČITIH tržišta/podataka, ne od
  više varijacija istog signala.
- Provjerena i sumnja da je problem u troškovima (svih 12 radi 3,5× više trgovina): minimalni prag
  trgovine 5% umjesto 1% smanjuje trgovine 6× (1816 → 298), ali rezultat ostaje isti (Sharpe
  0,92 → 0,93). Troškovi NISU uzrok. Zadani prag ostaje 1% (nije štiman); parametar
  `min_trade_fraction` je dodan u `run_portfolio_backtest`.

### Provjera look-ahead biasa

`app/checks.py:check_portfolio_no_lookahead` mijenja budućnost na svim parovima odjednom (dvije
vrste mutacije: skaliranje cijene i promjena volatilnosti) i provjerava da su signali, procjene
volatilnosti i težine prije reza identični. **Sama provjera je testirana namjernim bugom**: prva
verzija je PROŠLA s procjenom volatilnosti koja gleda 5 dana unaprijed (skaliranje cijene ×3 ne
mijenja log-povrate, a sve težine u tom razdoblju su bile 0). Popravljena verzija hvata i look-ahead
od samo 1 dana.

## Ograničenja koja treba znati

- Strategije su long-only na spotu (kupi/drži/prodaj) - nema shortanja ni poluge.
- Paper trading donosi odluke na svijećama dohvaćenim uživo s Coinbasea (dnevne ili satne, ovisno o
  izboru pri pokretanju runa), ne iz statične `data/kripto.sqlite` baze (ta baza se koristi samo za
  backtest).
- `dip_buy_volume`, `rsi_meanrev`, `stair_step_swing` i `stair_step_stochrsi` su u dosad pokrenutim
  testovima izgubile novac (potonja dva katastrofalno, 65-94%) - uključene su kao alat za daljnje
  istraživanje, ne kao preporuka (vidi "Stepenice - pošten nalaz" i "Stepenice v2 - pošten nalaz"
  iznad za potpun rezultat).
- "Wall Street"/zlato podaci pokrivaju tri indeksa i zlato preko Stooq-a, dnevna rezolucija. Stooq
  simboli (`^spx`, `^dji`, `^ndq`, `xauusd`) su standardna Stooq notacija, ali **nisu uživo
  potvrđeni IZ OVOG razvojnog okruženja** - direktan test odavde dobiva HTTP 404/connection reset
  na SVE simbole bez iznimke (čak i na `^spx` za koji smo prilično sigurni da je ispravan), što
  upućuje na Stooqov anti-bot/rate-limit filter na ovoj (dijeljenoj/proxy) mrežnoj adresi, ne na
  pogrešne simbole. Pokreni "Testiraj vezu" (odjeljak Wall Street) sa stvarnog servera (kućna/druga
  IP adresa) da dobiješ pouzdan odgovor - ako SE i dalje javi 404 baš ondje, tek tada ispravi simbol
  u `app/equity_client.py` (`INDEX_SYMBOLS`).
- Korelacija kripta/dioničko tržište/zlato koju `equity_filtered` i `multi_macro_filter` pokušavaju
  iskoristiti je poznata pojava zadnjih godina, ali nije fizikalni zakon - može oslabiti ili nestati.
- Optimizator pretražuje unaprijed zadane mreže parametara (`app/optimizer.py`, `DEFAULT_GRIDS`) -
  ne jamči da je pronašao globalno najbolju kombinaciju, samo najbolju unutar te mreže. Ograničen je
  na 400 kombinacija po pozivu (`MAX_COMBINATIONS`) radi razumnog vremena izvršavanja.
- Ni uspjeh na in-sample I out-of-sample razdoblju nije jamstvo budućeg profita - to je dva uzorka,
  ne beskonačno mnogo. Market režimi se mijenjaju; strategija provjerena na 2024–2026. ne mora raditi
  jednako u drugačijem tržišnom okruženju (npr. dugotrajni medvjeđi trend, nagla promjena kamatnih
  stopa, regulatorni šok).
- Reddit i regulatorni (SEC/CFTC) "sentiment" su **leksikonsko brojanje riječi**, ne trenirani NLP
  model - sarkazam, negacija ("nije bullish") i kontekst se NE prepoznaju. Tretiraj kao grub,
  transparentan proxy, ne kao pouzdanu klasifikaciju raspoloženja.
- Google Trends (`app/trends_client.py`, preko pytrends) je od svih dodanih izvora najkrhkiji -
  neslužbeni pristup koji Google može blokirati/promijeniti bez najave. ETF tokovi
  (`app/etf_client.py`) scrapaju javnu tablicu s farside.co.uk pa su slično krhki - provjeri Uvjete
  korištenja te stranice prije redovitog automatiziranog pristupa, kao i kod EOJN scrapera u Tender
  aplikaciji.
- CoinGecko besplatni tier ima strog rate limit (okvirno 10-30 poziva/min) - `sync_to_db` treba
  pokretati rijetko (ručno s dashboarda), ne u petlji ili automatski na svaki paper/live tick.
- "Implicitna cirkulirajuća ponuda" u `coingecko_client.py` (market cap / cijena) je aproksimacija,
  ne službeni podatak o ponudi - dovoljno dobra za grubi trend, ne za precizan tokenomics izračun.
- `macro_signal_composite` treba sve 4 serije (FRED, Reddit, regulativa, ETF tok) sinkronizirane da
  bi uopće pokrenuo backtest - namjerno strože od "nedostajući glas se ne broji" unutar same odluke
  (to pravilo vrijedi tek kad su serije sinkronizirane, ali pojedini dani unutar njih nedostaju).
- `derivatives_extremes` je kontrarijanski/reversal signal (kladi se na preokret nakon ekstrema), za
  razliku od trend-prateećih strategija u ovom projektu - testira drukčiju tezu, nije "poboljšana
  verzija" nečeg postojećeg. Pragovi ekstrema (`extreme_negative`/`extreme_positive`) su proizvoljno
  postavljeni početni pokušaji, ne kalibrirani na povijesnu distribuciju funding ratea - koristi
  optimizator (odjeljak 7) prije vjerovanja bilo kojoj konkretnoj vrijednosti.
- `github_client.py` prati samo broj commitova, ne i njihovu kvalitetu/veličinu - jedan commit koji
  mijenja jedan redak broji se jednako kao veliki refactor. Grub proxy za aktivnost, ne za kvalitetu
  razvoja.
- CryptoPanic je mijenjao verzije API-ja u prošlosti - ako "Testiraj vezu" ne uspije, prvo provjeri
  trenutnu dokumentaciju na cryptopanic.com/developers/api/ prije traženja bugova u
  `app/cryptopanic_client.py`.
- `binance_history_client.py` sinkronizira cijelu dostupnu povijest pri svakom pozivu (nema
  inkrementalnog "samo nove podatke" moda) - za coinove s dugom poviješću (DOGE postoji od 2019.)
  prvi sync može potrajati zbog straniciranja Binance API-ja (max 1000 svijeća po pozivu).
- Rezultat backtesta/optimizatora na tvojim konkretnim coinovima (odjeljci 4 i 7) NIJE unaprijed
  poznat - možda će neka strategija pokazati prednost, možda neće nijedna, kao što se dogodilo s
  BTC/ETH/SOL (vidi "Ključni nalaz" i "Pretraga po više parova" gore). Pokreni ga i pogledaj
  rezultat pošteno, ne traži potvrdu onoga što bi želio čuti.
- "Signali kupi/prodaj" (odjeljak 2) rade uvijek na NAJNOVIJOJ dostupnoj svijeći, koja kod 4h
  intervala može biti još "u tijeku" (nedovršena) - Binance klines endpoint je ne isključuje
  automatski. Za živi signal to je razumno (želiš najsvježiju cijenu), ali znači da se vrijednost
  može malo promijeniti do kraja te 4h svijeće - nije isto kao strogo zatvorena povijesna svijeća
  korištena u backtestu.
- Kratkoročni preset u "Signali kupi/prodaj" treba sinkronizirane 4h podatke da bi ga mogao i
  backtestirati (ne samo gledati živi signal) - koristi `interval: "4h"` pri sync pozivu
  (`/api/binance-history/sync`) ili dashboard sekciju 3 s odgovarajućim odabirom intervala.
