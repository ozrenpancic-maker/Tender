import { NextResponse } from "next/server";
import { getOrCreateSearchProfile, profileToCriteria } from "@/lib/searchProfile";
import { searchTed } from "@/lib/providers/ted";
import { searchEojn, fetchEojnDebugHtml } from "@/lib/providers/eojn";

// Dijagnostički endpoint - ne sprema ništa u bazu, samo provjerava mogu li se izvori uopće dohvatiti
// i parsirati. Koristan za provjeru/podešavanje providera nakon deploya u okruženje s internet
// pristupom (vidi napomene u src/lib/providers/ted.ts i eojn.ts).
export async function GET() {
  const profile = await getOrCreateSearchProfile();
  const criteria = profileToCriteria(profile);

  const [ted, eojn, eojnDebug] = await Promise.all([
    searchTed(criteria),
    searchEojn(criteria),
    fetchEojnDebugHtml(criteria),
  ]);

  return NextResponse.json({
    ted: { ok: ted.ok, message: ted.message, sampleCount: ted.listings.length, sample: ted.listings.slice(0, 3) },
    eojn: {
      ok: eojn.ok,
      message: eojn.message,
      sampleCount: eojn.listings.length,
      sample: eojn.listings.slice(0, 3),
      debug: eojnDebug,
    },
  });
}

export const dynamic = "force-dynamic";
