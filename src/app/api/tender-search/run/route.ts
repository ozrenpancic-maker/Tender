import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { getOrCreateSearchProfile, profileToCriteria } from "@/lib/searchProfile";
import { searchTed } from "@/lib/providers/ted";
import { searchEojn } from "@/lib/providers/eojn";
import type { NormalizedListing } from "@/lib/providers/types";

async function upsertListings(listings: NormalizedListing[]) {
  let created = 0;
  let updated = 0;

  for (const l of listings) {
    const existing = await prisma.tenderListing.findUnique({
      where: { source_externalId: { source: l.source, externalId: l.externalId } },
    });

    const data = {
      title: l.title,
      authority: l.authority ?? null,
      cpv: l.cpv ?? null,
      publishedDate: l.publishedDate ?? null,
      deadline: l.deadline ?? null,
      estimatedValue: l.estimatedValue ?? null,
      currency: l.currency ?? "EUR",
      noticeType: l.noticeType ?? null,
      url: l.url ?? null,
      rawExcerpt: l.rawExcerpt ?? null,
    };

    if (existing) {
      await prisma.tenderListing.update({ where: { id: existing.id }, data });
      updated++;
    } else {
      await prisma.tenderListing.create({ data: { source: l.source, externalId: l.externalId, ...data } });
      created++;
    }
  }

  return { created, updated };
}

export async function POST() {
  const profile = await getOrCreateSearchProfile();
  const criteria = profileToCriteria(profile);

  const results: { ted?: string; eojn?: string } = {};
  let created = 0;
  let updated = 0;

  if (profile.sourceTed) {
    const ted = await searchTed(criteria);
    results.ted = ted.message;
    if (ted.ok) {
      const r = await upsertListings(ted.listings);
      created += r.created;
      updated += r.updated;
    }
  }

  if (profile.sourceEojn) {
    const eojn = await searchEojn(criteria);
    results.eojn = eojn.message;
    if (eojn.ok) {
      const r = await upsertListings(eojn.listings);
      created += r.created;
      updated += r.updated;
    }
  }

  return NextResponse.json({ created, updated, diagnostics: results });
}

export const dynamic = "force-dynamic";
