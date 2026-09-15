import * as cheerio from "cheerio";
import type { NormalizedListing, ProviderResult, SearchCriteria } from "./types";

// VAŽNA NAPOMENA O POUZDANOSTI:
// EOJN RH (Elektronički oglasnik javne nabave RH) nema poznat javni REST API niti feed otvorenih
// podataka. Ovo je HTML scraper koji NIJE testiran uživo jer ovo razvojno okruženje nema izlazni
// pristup internetu - stvarna struktura pretraživača i HTML-a stranice nije provjerena. Prije
// puštanja u produkciju:
//   1. Provjeri Uvjete korištenja EOJN portala (eojn.nn.hr) - poštuje li automatizirani pristup;
//      ako ne, ovaj provider treba isključiti (SOURCE_EOJN=false / isključi u profilu pretrage).
//   2. Pokreni /api/tender-search/test-connection iz okoline koja ima pristup internetu i pogledaj
//      `rawHtmlSample` u odgovoru - ako selektori ispod ne pronađu zapise, prilagodi ih prema
//      stvarnom HTML-u (sve je izolirano u ovoj datoteci).
//   3. Poštuj razumno ograničenje učestalosti poziva (ne pokretati pretragu prečesto).

const EOJN_BASE_URL = process.env.EOJN_BASE_URL || "https://eojn.nn.hr";
const EOJN_SEARCH_PATH = process.env.EOJN_SEARCH_PATH || "/Oglasnik/";
const USER_AGENT = "TenderOP/0.1 (automatska pretraga natjecaja za ponuditelja; kontakt: vlasnik racuna)";

function buildSearchUrl(criteria: SearchCriteria): string {
  const url = new URL(EOJN_SEARCH_PATH, EOJN_BASE_URL);
  if (criteria.keywords.length > 0) url.searchParams.set("q", criteria.keywords.join(" "));
  if (criteria.cpvCodes.length > 0) url.searchParams.set("cpv", criteria.cpvCodes.join(","));
  if (criteria.county) url.searchParams.set("zupanija", criteria.county);
  return url.toString();
}

function parseHrDate(text: string): Date | undefined {
  const match = text.match(/(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4})/);
  if (!match) return undefined;
  const [, d, m, y] = match;
  const date = new Date(Number(y), Number(m) - 1, Number(d));
  return Number.isNaN(date.getTime()) ? undefined : date;
}

interface Candidate {
  title: string;
  href: string;
  contextText: string;
}

function extractCandidates($: cheerio.CheerioAPI): Candidate[] {
  const candidates: Candidate[] = [];

  // Strategija 1: linkovi koji vode na detalje objave (naslov obavijesti tipično je link)
  $("a").each((_, el) => {
    const href = $(el).attr("href") || "";
    const text = $(el).text().trim();
    if (!text || text.length < 8) return;
    if (!/oglas|dokument|detalj|nabav|predmet|javn/i.test(href) && !/oglas|nabav/i.test(text)) return;

    const context = $(el).closest("tr, li, div").text().replace(/\s+/g, " ").trim();
    candidates.push({ title: text, href, contextText: context });
  });

  return candidates;
}

export async function searchEojn(criteria: SearchCriteria): Promise<ProviderResult> {
  const searchUrl = buildSearchUrl(criteria);

  let response: Response;
  try {
    response = await fetch(searchUrl, {
      headers: { "User-Agent": USER_AGENT, Accept: "text/html" },
    });
  } catch (err) {
    return {
      ok: false,
      listings: [],
      message: `Ne mogu spojiti na EOJN RH (${searchUrl}): ${
        err instanceof Error ? err.message : String(err)
      }`,
    };
  }

  if (!response.ok) {
    return {
      ok: false,
      listings: [],
      message: `EOJN RH vratio HTTP ${response.status} za ${searchUrl}. Provjeri EOJN_BASE_URL / EOJN_SEARCH_PATH.`,
    };
  }

  const html = await response.text();
  const $ = cheerio.load(html);
  const candidates = extractCandidates($);

  if (candidates.length === 0) {
    return {
      ok: false,
      listings: [],
      message: `EOJN RH: stranica je dohvaćena (HTTP ${response.status}, ${html.length} znakova), ali scraper nije prepoznao nijednu stavku natječaja. Selektori u src/lib/providers/eojn.ts vjerojatno trebaju prilagodbu stvarnoj HTML strukturi (pogledaj rawHtmlSample preko /api/tender-search/test-connection).`,
    };
  }

  const listings: NormalizedListing[] = candidates.slice(0, 50).map((c, i) => {
    const url = new URL(c.href, EOJN_BASE_URL).toString();
    return {
      source: "eojn",
      externalId: url,
      title: c.title,
      authority: undefined,
      cpv: criteria.cpvCodes.length > 0 ? criteria.cpvCodes.join(", ") : undefined,
      publishedDate: undefined,
      deadline: parseHrDate(c.contextText),
      estimatedValue: undefined,
      currency: "EUR",
      noticeType: undefined,
      url,
      rawExcerpt: c.contextText.slice(0, 500) || `candidate-${i}`,
    };
  });

  return {
    ok: true,
    listings,
    message: `EOJN RH: pronađeno ${listings.length} mogućih zapisa (heuristička ekstrakcija - provjeri rawExcerpt polje radi točnosti).`,
  };
}

export async function fetchEojnDebugHtml(criteria: SearchCriteria): Promise<{ url: string; status: number; sample: string } | { url: string; error: string }> {
  const url = buildSearchUrl(criteria);
  try {
    const response = await fetch(url, { headers: { "User-Agent": USER_AGENT } });
    const html = await response.text();
    return { url, status: response.status, sample: html.slice(0, 1500) };
  } catch (err) {
    return { url, error: err instanceof Error ? err.message : String(err) };
  }
}
