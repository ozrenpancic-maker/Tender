import type { NormalizedListing, ProviderResult, SearchCriteria } from "./types";

// NAPOMENA O POUZDANOSTI:
// Ovo je implementacija prema javno dostupnoj dokumentaciji TED API v3 (docs.ted.europa.eu/api)
// kakva je poznata u trenutku pisanja koda - u ovom razvojnom okruženju nema izlaznog pristupa
// internetu pa endpoint, nazivi polja i format odgovora NISU uživo testirani. Ako "Testiraj vezu"
// (/api/tender-search/test-connection) prijavi grešku parsiranja ili 0 rezultata unatoč HTTP 200,
// provjeri stvarni odgovor (vidi `rawExcerpt` na svakom zapisu ili dijagnostičku poruku) i po potrebi
// prilagodi TED_API_BASE / mapiranje polja ispod - promjene su izolirane u ovoj datoteci.

const TED_API_BASE = process.env.TED_API_BASE || "https://api.ted.europa.eu/v3/notices/search";
const TED_API_KEY = process.env.TED_API_KEY; // opcionalno - TED trenutno nudi besplatnu javnu pretragu, ključ nije uvijek obavezan

function buildExpertQuery(criteria: SearchCriteria): string | null {
  const clauses: string[] = [];

  if (criteria.cpvCodes.length > 0) {
    clauses.push(`classification-cpv IN (${criteria.cpvCodes.join(" ")})`);
  }
  if (criteria.keywords.length > 0) {
    const kw = criteria.keywords.map((k) => `notice-title~"${k.replace(/"/g, "")}"`).join(" OR ");
    clauses.push(`(${kw})`);
  }

  if (clauses.length === 0) return null;
  return clauses.join(" AND ");
}

function dig(obj: unknown, keys: string[]): unknown {
  for (const key of keys) {
    const value = (obj as Record<string, unknown>)?.[key];
    if (value !== undefined && value !== null) return value;
  }
  return undefined;
}

function asString(value: unknown): string | undefined {
  if (Array.isArray(value)) return value.map((v) => asString(v)).filter(Boolean).join(", ") || undefined;
  if (value && typeof value === "object") {
    const obj = value as Record<string, unknown>;
    const localized = obj.eng ?? obj.hrv ?? Object.values(obj)[0];
    return typeof localized === "string" ? localized : undefined;
  }
  return typeof value === "string" ? value : value != null ? String(value) : undefined;
}

function asNumber(value: unknown): number | undefined {
  if (typeof value === "number") return value;
  if (typeof value === "string") {
    const n = Number(value.replace(/[^\d.,-]/g, "").replace(",", "."));
    return Number.isFinite(n) ? n : undefined;
  }
  return undefined;
}

function asDate(value: unknown): Date | undefined {
  const s = asString(value);
  if (!s) return undefined;
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? undefined : d;
}

export async function searchTed(criteria: SearchCriteria): Promise<ProviderResult> {
  const query = buildExpertQuery(criteria);
  if (!query) {
    return {
      ok: false,
      listings: [],
      message: "Dodaj barem jedan CPV kod ili ključnu riječ da bi TED pretraga imala smisla.",
    };
  }

  let response: Response;
  try {
    response = await fetch(TED_API_BASE, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(TED_API_KEY ? { "X-Api-Key": TED_API_KEY } : {}),
      },
      body: JSON.stringify({
        query,
        fields: [
          "publication-number",
          "notice-title",
          "buyer-name",
          "classification-cpv",
          "publication-date",
          "deadline-receipt-tender-date-lot",
          "estimated-value-glo",
          "notice-type",
        ],
        page: 1,
        limit: 50,
        scope: "ACTIVE",
      }),
    });
  } catch (err) {
    return {
      ok: false,
      listings: [],
      message: `Ne mogu spojiti na TED API (${TED_API_BASE}): ${
        err instanceof Error ? err.message : String(err)
      }`,
    };
  }

  if (!response.ok) {
    const body = await response.text().catch(() => "");
    return {
      ok: false,
      listings: [],
      message: `TED API vratio HTTP ${response.status}. ${body.slice(0, 300)}`,
    };
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch (err) {
    return {
      ok: false,
      listings: [],
      message: `TED API odgovor nije valjan JSON: ${err instanceof Error ? err.message : String(err)}`,
    };
  }

  const notices = (dig(data, ["notices", "results", "items"]) ?? (Array.isArray(data) ? data : [])) as unknown[];

  if (!Array.isArray(notices)) {
    return {
      ok: false,
      listings: [],
      message: `TED API vratio neočekivan oblik odgovora - provjeri mapiranje u src/lib/providers/ted.ts. Sirovi odgovor: ${JSON.stringify(
        data,
      ).slice(0, 500)}`,
    };
  }

  const listings: NormalizedListing[] = notices.map((notice, i) => {
    const externalId =
      asString(dig(notice, ["publication-number", "ND", "id"])) ?? `unknown-${i}-${Date.now()}`;
    return {
      source: "ted",
      externalId,
      title: asString(dig(notice, ["notice-title", "title"])) ?? "(bez naslova)",
      authority: asString(dig(notice, ["buyer-name", "organisation-name-buyer"])),
      cpv: asString(dig(notice, ["classification-cpv", "cpv"])),
      publishedDate: asDate(dig(notice, ["publication-date", "publicationDate"])),
      deadline: asDate(dig(notice, ["deadline-receipt-tender-date-lot", "deadline"])),
      estimatedValue: asNumber(dig(notice, ["estimated-value-glo", "value"])),
      currency: asString(dig(notice, ["estimated-value-cur", "currency"])) || "EUR",
      noticeType: asString(dig(notice, ["notice-type", "noticeType"])),
      url: `https://ted.europa.eu/en/notice/-/detail/${externalId}`,
      rawExcerpt: JSON.stringify(notice).slice(0, 500),
    };
  });

  return {
    ok: true,
    listings,
    message: `TED: pronađeno ${listings.length} obavijesti za upit "${query}".`,
  };
}
