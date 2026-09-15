# Tender OP – asistent za javnu nabavu

Web aplikacija koja pomaže ponuditeljima u javnoj nabavi: učitaš natječajnu dokumentaciju, a AI ti
sastavi sažetak natječaja, ključne zahtjeve (rokove, kriterije, vrijednost) i checklistu svih
dokumenata koje trebaš pripremiti i predati uz ponudu.

## Trenutno stanje (MVP)

- **Projekti** – svaki natječaj na kojem radiš je zaseban projekt.
- **Upload dokumentacije** – PDF, DOCX ili TXT (natječajna dokumentacija i vlastiti dokumenti tvrtke).
- **AI analiza** (Claude) – iz učitane natječajne dokumentacije izvlači:
  - sažetak natječaja,
  - ključne zahtjeve (rok, procijenjenu vrijednost, kriterij odabira, uvjete sposobnosti…),
  - checklistu dokumenata za ponudu, grupiranu po kategoriji, s mogućnošću označavanja "pripremljeno".
- **Profil tvrtke** (`/company`) – podaci tvrtke (OIB, adresa, IBAN, opis/reference) i vlastiti
  predlošci (obrasci, troškovnik) koji se koriste u generiranju ponude.
- **Nacrt ponude (.docx)** – AI na temelju analize natječaja, checkliste i profila tvrtke sastavlja
  tekstualni dio ponude (uvodno pismo, izjave, tehnički opis) i izvozi ga kao Word dokument za daljnju
  doradu. Ne popunjava službene obrasce naručitelja niti izmišlja cijene/činjenice — mjesta koja
  nedostaju označava s `[DOPUNITI: ...]`.
- **Praćenje konkurencije** (`/konkurencija`) – baza javno objavljenih dodjela ugovora (pobjednik,
  naručitelj, CPV, vrijednost, proizvodi/usluge), uvoz putem CSV-a ili ručni unos, filtriranje po
  konkurentu/CPV-u/pojmu, te **AI analiza cijena i proizvoda** nad filtriranim podacima (raspon cijena,
  najčešći proizvodi, pozicioniranje ponude).
- **Automatska pretraga natječaja** (`/pretraga-natjecaja`) – postaviš kriterije (CPV kodovi, ključne
  riječi, raspon vrijednosti, županija), pretraga se pokreće preko **TED API-ja** (EU) i **scrapera za
  EOJN RH**, rezultati se spremaju i mogu jednim klikom postati novi projekt (uz automatski predložen
  naziv, naručitelj i rok). Ima gumb "Testiraj vezu" koji odmah pokaže je li dohvat uspio i zašto ako
  nije — pogledaj **Ograničenja** ispod prije nego se osloniš na EOJN dio.

## Pokretanje lokalno

1. Instaliraj ovisnosti:
   ```bash
   npm install
   ```
2. Kopiraj `.env.example` u `.env` i postavi:
   - `DATABASE_URL` – ostavi `file:./dev.db` za lokalni SQLite
   - `ANTHROPIC_API_KEY` – tvoj Anthropic API ključ (potreban za AI analizu dokumentacije)
3. Pripremi bazu:
   ```bash
   npx prisma migrate dev --name init
   ```
4. Pokreni dev server:
   ```bash
   npm run dev
   ```
5. Otvori [http://localhost:3000](http://localhost:3000).

## Arhitektura

- **Next.js 14 (App Router) + TypeScript + Tailwind** – frontend i API rute u istom projektu.
- **Prisma + SQLite** – `Project`, `Document`, `ChecklistItem`, `Requirement`, `Analysis`,
  `CompanyProfile`, `CompanyTemplate`, `GeneratedOffer`, `Competitor`, `CompetitorAward` modeli (vidi
  `prisma/schema.prisma`). SQLite je dovoljan za MVP; za produkciju je lako prebaciti na Postgres
  promjenom `provider` i `DATABASE_URL`.
- **`src/lib/extractText.ts`** – izvlačenje teksta iz PDF/DOCX/TXT datoteka.
- **`src/lib/analyze.ts`** – poziv Anthropic API-ja (Claude) sa strukturiranim promptom koji vraća
  JSON (sažetak, zahtjevi, checklist) za analizu natječajne dokumentacije.
- **`src/lib/generateOffer.ts`** – poziv Claude-a za nacrt teksta ponude + izgradnja `.docx` datoteke
  (paket `docx`).
- **`src/lib/analyzeCompetitors.ts`** – poziv Claude-a za analizu cijena/proizvoda nad podacima o
  dodjelama ugovora.
- **`src/lib/csv.ts`** – jednostavan CSV parser za uvoz podataka o dodjelama ugovora.
- **`src/lib/providers/ted.ts`** i **`src/lib/providers/eojn.ts`** – dohvat natječaja s TED API-ja
  (Expert Query Language upiti) i EOJN RH (HTML scraper), s obrambenim parsiranjem i dijagnostičkim
  porukama umjesto tihog pada. Konfigurabilno preko `TED_API_BASE`, `TED_API_KEY`, `EOJN_BASE_URL`,
  `EOJN_SEARCH_PATH` env varijabli.
- Uploadane datoteke, predlošci tvrtke i generirani nacrti ponuda spremaju se lokalno u `uploads/`
  (izvan gita).

## Ograničenja koja treba znati

- Nacrt ponude je **novi** Word dokument sastavljen prema sadržaju tvojih predložaka, ne izmjena
  izvorne .docx datoteke uz očuvanje njenog točnog formatiranja/polja. Za popunjavanje službenih
  obrazaca naručitelja (ESPD, troškovnik) i dalje je potreban ručni unos u te obrasce.
- Podaci o konkurenciji temelje se isključivo na **javno objavljenim** dodjelama ugovora (EOJN
  RH / TED "Obavijest o dodjeli ugovora"). Ponude koje nisu pobijedile nisu javne i nisu dostupne.
- **TED integracija je napisana prema javnoj dokumentaciji, ali nije uživo testirana** – ovaj razvojni
  container nema izlazni pristup internetu (izvan dopuštenog popisa domena), pa endpoint/nazivi polja
  TED API-ja nisu potvrđeni protiv stvarnog odgovora. Prvi put kad se pokrene s pravim internet
  pristupom, provjeri "Testiraj vezu" na `/pretraga-natjecaja` — ako prijavi grešku parsiranja, popravak
  je izoliran u `src/lib/providers/ted.ts`.
- **EOJN RH nema poznat javni API** – scraper u `src/lib/providers/eojn.ts` je best-effort HTML
  parsiranje koje **nije provjereno protiv stvarne stranice** (isti razlog kao gore) i vjerojatno će
  trebati podešavanje selektora nakon prvog pokretanja. Prije korištenja u produkciji obavezno provjeri
  Uvjete korištenja EOJN portala vezano uz automatizirani pristup.

## Napomena o sigurnosti

Ovo je razvojni MVP: nema autentikacije korisnika niti multi-tenant izolacije. Prije bilo kakve
produkcijske upotrebe (posebice ako će raditi s podacima više tvrtki) potrebno je dodati
autentikaciju, autorizaciju po korisniku/tvrtki i pohranu datoteka izvan lokalnog diska (npr. S3).
