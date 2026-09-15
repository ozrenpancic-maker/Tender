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
- **Pretraga natječaja (EOJN RH / TED)** – planirana faza, vidi `/pretraga-natjecaja` za roadmap.
  Automatsko preuzimanje dodjela ugovora s tih portala za sekciju "Konkurencija" je dio iste faze.

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
- Uploadane datoteke, predlošci tvrtke i generirani nacrti ponuda spremaju se lokalno u `uploads/`
  (izvan gita).

## Ograničenja koja treba znati

- Nacrt ponude je **novi** Word dokument sastavljen prema sadržaju tvojih predložaka, ne izmjena
  izvorne .docx datoteke uz očuvanje njenog točnog formatiranja/polja. Za popunjavanje službenih
  obrazaca naručitelja (ESPD, troškovnik) i dalje je potreban ručni unos u te obrasce.
- Podaci o konkurenciji temelje se isključivo na **javno objavljenim** dodjelama ugovora (EOJN
  RH / TED "Obavijest o dodjeli ugovora"). Ponude koje nisu pobijedile nisu javne i nisu dostupne.
- Automatsko preuzimanje s EOJN RH / TED portala (umjesto ručnog CSV uvoza) nije još implementirano —
  vidi `/pretraga-natjecaja`.

## Napomena o sigurnosti

Ovo je razvojni MVP: nema autentikacije korisnika niti multi-tenant izolacije. Prije bilo kakve
produkcijske upotrebe (posebice ako će raditi s podacima više tvrtki) potrebno je dodati
autentikaciju, autorizaciju po korisniku/tvrtki i pohranu datoteka izvan lokalnog diska (npr. S3).
