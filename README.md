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
- **Pretraga natječaja (EOJN RH / TED)** i **automatsko generiranje ponude** – planirane sljedeće faze,
  vidi `/pretraga-natjecaja` za roadmap.

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
- **Prisma + SQLite** – `Project`, `Document`, `ChecklistItem`, `Requirement`, `Analysis` modeli
  (vidi `prisma/schema.prisma`). SQLite je dovoljan za MVP; za produkciju je lako prebaciti na
  Postgres promjenom `provider` i `DATABASE_URL`.
- **`src/lib/extractText.ts`** – izvlačenje teksta iz PDF/DOCX/TXT datoteka.
- **`src/lib/analyze.ts`** – poziv Anthropic API-ja (Claude) sa strukturiranim promptom koji vraća
  JSON (sažetak, zahtjevi, checklist).
- Uploadane datoteke spremaju se lokalno u `uploads/<projectId>/` (izvan gita).

## Napomena o sigurnosti

Ovo je razvojni MVP: nema autentikacije korisnika niti multi-tenant izolacije. Prije bilo kakve
produkcijske upotrebe (posebice ako će raditi s podacima više tvrtki) potrebno je dodati
autentikaciju, autorizaciju po korisniku/tvrtki i pohranu datoteka izvan lokalnog diska (npr. S3).
