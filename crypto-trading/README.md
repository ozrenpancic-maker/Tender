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
3. **Walk-forward validacija** (`app/ml/dataset.py`) - podaci (pooled BTC/ETH/SOL, parovi se NE
   kodiraju kao značajka) podijeljeni kronološki u foldove; za svaki fold: train (expanding
   window) → zadnjih 20% toga je kalibracijski skup (izolirana kalibracija vjerojatnosti preko
   `CalibratedClassifierCV` s izotoničnom regresijom) → test na SLJEDEĆEM, još neviđenom bloku.
   Nijedan test primjer nikad nije korišten za fit ili kalibraciju bilo kojeg modela koji ga
   predviđa - standardna zaštita od look-ahead/data leakage biasa.
4. **Kalibracija i poštena provjera** (`app/ml/calibration.py`) - Brier score (multiklasni),
   log loss, reliability dijagram (pouzdanost vs stvarna točnost po binovima), i NAIVNA bazna
   linija (model koji uvijek predviđa udio klasa iz treninga, "ne znam ništa"). Model se smatra
   **validiranim** samo ako je njegov Brier score barem 2% relativno bolji od bazne linije na
   walk-forward testu (pravilo #12/#13: nevalidiran model ne aktivira live preporuku).

### Pošten rezultat prvog treniranja (23.11.2026., nad podacima dostupnim u ovom razvojnom okruženju)

| Horizont | Uzorak (n) | LightGBM Brier | Bazna linija Brier | Validiran? |
|---|---|---|---|---|
| 1h | 7533 (resample 5-min→1h, 113 dana) | 0,1107 | 0,1112 | **NE** (razlika unutar šuma) |
| 4h | 1431 (resample 5-min→4h, 113 dana) | 0,4057 | 0,3784 | **NE** (lošiji od bazne linije) |
| 24h | 8459 (prava dnevna povijest, 2017/2020-2026) | 0,5262 | 0,5250 | **NE** |
| 7d | 8441 (prava dnevna povijest, label 7 dana unaprijed) | 0,5669 | 0,5562 | **NE** |

**Nijedan horizont trenutno nije prošao validaciju.** `/api/predictions` zato za sve coinove/
horizonte vraća `"NEMA DOVOLJNO POUZDANIH PODATAKA"` - to je pravilo #8 na djelu (nepouzdan model →
WAIT, ne izmišljena sigurnost), ne greška u kodu. Ovo je konzistentno s ranijim nalazom u ovom
projektu (vidi "Ključni nalaz" ispod) da jednostavni mehanički signali na BTC/ETH/SOL ne pokazuju
robusnu prednost nad "ne radi ništa" - ML pristup s ovim značajkama i ovom količinom podataka to
potvrđuje na stroži, kalibriran način, ne osporava.

Što bi moglo promijeniti ovo (poštene, ne zagarantirane ideje za sljedeću iteraciju):
- Više povijesti za 1h/4h (sinkroniziraj izravno s Binancea nekoliko godina 1h/4h svijeća, ne samo
  113 dana resampliranih iz 5-min) - trenutni uzorak za 4h je posebno tanak (1431 primjera).
- Dodatne značajke iz već postojećih klijenata u ovoj app-i (makro, derivatives funding/OI,
  sentiment, on-chain) - trenutni model vidi SAMO cijenu/volumen, ništa od ostatka faza 1 podataka.
- Drugi feature inženjering (npr. relativna snaga parova, market regime kao ulazna značajka).
- Prag "validiran" (2% relativno bolji Brier) je namjerno strog da se spriječi lažno pozitivan
  rezultat (prva verzija s pragom 0% je "validirala" 1h horizont s poboljšanjem od samo 0,0005 -
  vjerojatno šum, ne stvarna vještina, zbog jako neravnomjerne raspodjele klasa na 1h).

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
pip install lightgbm scikit-learn joblib   # ako već nisu instalirani
python3 -m app.ml.train
```

Zapisuje `data/models/<horizont>_lgbm.joblib` i `data/models/metadata.json` (walk-forward metrike,
`validated` zastavica koju `app/ml/engine.py` čita). Siguran je za ponovno pokretanje - briše i
ponovno piše iste datoteke, ne mijenja ništa drugo u bazi.

### Razlozi za/protiv (`reasons_for`/`reasons_against`)

Namjerno NISU SHAP vrijednosti (ta ovisnost bi se mogla dodati u fazi 6 ako pokaže mjerljivu
korist) - to su jednostavna, provjerljiva pravila koja izravno čitaju vrijednost značajke i
uspoređuju s dokumentiranim pragom (npr. "RSI14 < 30 → razlog za", "cijena iznad EMA200 → razlog
za"). Transparentnije za sada nego aproksimacija važnosti značajki iz modela, iako manje precizno
povezano sa stvarnom odlukom tog konkretnog modela.

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

**Kako radi**: `compute_signal(pair, horizon)` dohvaća najnovije svijeće uživo (Binance, bez ključa)
i pokreće `decide()` ISTE funkcije koja se koristi u backtestu, dva puta - jednom s
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
samo na BTC/ETH/SOL. Ako "Osvježi signale" javi grešku, isti je razlog kao svugdje u ovom README-u
- ovo razvojno okruženje nema izlazni pristup internetu da bi se Binance pozivi mogli uživo
testirati; logika je potvrđena korištenjem stvarnih (ne izmišljenih) 4h BTC podataka već u bazi.

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
  ChatGPT-ovim paralelnim istraživanjem" iznad.
- **`app/coinbase_client.py`** — ISKLJUČIVO javni cjenovni feed (bez ključa). Autenticirani dio je
  uklonjen (KriptoMVP 4.4 pravila) - vidi "Isključivo savjetnik/simulator" ispod.
- **`app/ml/`** — AI Prediction Engine (faza 3): `features.py` (značajke), `labels.py` (3-klasni
  label, trošak+volatilnost-skalirana granica), `dataset.py` (pooled BTC/ETH/SOL, walk-forward
  foldovi), `calibration.py` (Brier/log loss/reliability + bazna linija), `train.py` (LightGBM +
  logistička regresija), `engine.py` (uživo predikcija, WAIT gate za nevalidirane horizonte). Vidi
  "AI Prediction Engine" iznad.
- **`app/equity_client.py`** — dnevni podaci za S&P 500 / Dow / Nasdaq / zlato sa Stooq-a (javno,
  bez ključa), za makro-filter strategije. `app/aux.py` poravnava kripto (trguje se 7 dana u tjednu)
  i equity/zlato (zatvoreno vikendom) kalendare uzimanjem zadnje poznate cijene na/prije danog dana.
- **`app/binance_history_client.py`** — povijest cijena za proizvoljan Binance par i interval
  (1d/4h/1h), izravno u `candle` tablicu (source_id='binance') - isti oblik kao izvorni podaci, pa
  odmah radi sa svim postojećim strategijama/backtestom/optimizatorom.
- **`app/signals.py`** — trenutni (uživo) signal kupi/prodaj po dva horizonta, koristi iste
  `decide()` funkcije kao backtest, pozvane jednom na zadnju svijeću umjesto u petlji. Vidi
  "Signali kupi/prodaj" iznad.
- **`app/indicators.py`** — čiste funkcije za EMA, MACD, Stochastic RSI, ROC, OBV, ATR, Bollinger
  Bands - bez vanjskih poziva, koriste ih `technical_composite` i `macro_signal_composite`.
- **`app/macro_store.py`** + `macro_series` tablica — generička pohrana ne-OHLC serija (jedna
  vrijednost po danu), zajednička za sve nove makro/sentiment izvore. `app/aux.py` ima odgovarajuće
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

## Isključivo savjetnik/simulator (KriptoMVP 4.4 nepromjenjiva pravila)

Aplikacija **nikada ne izvršava prave naloge** i ne traži Coinbase trgovačke (autenticirane) API
ključeve niti pristup računu/novčaniku - ta mogućnost (`app/live_engine.py`, autenticirani dio
`app/coinbase_client.py`, `/api/live/*` rute, dashboard sekcija "Live trgovanje") je namjerno
potpuno uklonjena iz koda, ne samo isključena zastavicom - vidi git povijest ako ti treba za
referencu. Koristi se isključivo javni, read-only Coinbase cjenovni feed (bez ključa), za paper
trading i backtest.

## Ograničenja koja treba znati

- Strategije su long-only na spotu (kupi/drži/prodaj) - nema shortanja ni poluge.
- Paper trading donosi odluke na dnevnim svijećama dohvaćenim uživo s Coinbasea, ne iz statične
  `data/kripto.sqlite` baze (ta baza se koristi samo za backtest).
- `dip_buy_volume` i `rsi_meanrev` su u jedinom dosad pokrenutom testu izgubili novac - uključene
  su kao alat za daljnje istraživanje, ne kao preporuka.
- "Wall Street"/zlato podaci pokrivaju tri indeksa i zlato preko Stooq-a, dnevna rezolucija. Stooq
  simboli (`^spx`, `^dji`, `^ndq`, `xauusd`) nisu uživo potvrđeni - ako "Testiraj vezu" javi grešku
  za neki od njih, ispravi simbol u `app/equity_client.py` (`INDEX_SYMBOLS`).
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
