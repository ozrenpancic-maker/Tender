import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { parseCsv } from "@/lib/csv";

// Očekivani CSV stupci (redoslijed nije bitan, header mora sadržavati ova imena):
// winnerName, authority, cpv, tenderTitle, value, currency, awardDate, productsText, sourceUrl
const REQUIRED_COLUMNS = ["winnerName", "tenderTitle"];

export async function POST(req: NextRequest) {
  const formData = await req.formData();
  const file = formData.get("file");

  if (!(file instanceof File)) {
    return NextResponse.json({ error: "Nedostaje CSV datoteka." }, { status: 400 });
  }

  const text = await file.text();
  const rows = parseCsv(text);

  if (rows.length < 2) {
    return NextResponse.json({ error: "CSV datoteka je prazna ili nema podataka." }, { status: 400 });
  }

  const header = rows[0].map((h) => h.trim());
  for (const col of REQUIRED_COLUMNS) {
    if (!header.includes(col)) {
      return NextResponse.json(
        { error: `CSV mora imati stupac "${col}". Očekivani stupci: winnerName, authority, cpv, tenderTitle, value, currency, awardDate, productsText, sourceUrl.` },
        { status: 400 },
      );
    }
  }

  const idx = (name: string) => header.indexOf(name);
  const dataRows = rows.slice(1);

  const competitors = await prisma.competitor.findMany();
  const competitorByName = new Map(competitors.map((c) => [c.name.toLowerCase(), c.id]));

  let imported = 0;
  const errors: string[] = [];

  for (const [i, r] of dataRows.entries()) {
    const winnerName = (r[idx("winnerName")] || "").trim();
    const tenderTitle = (r[idx("tenderTitle")] || "").trim();
    if (!winnerName || !tenderTitle) {
      errors.push(`Redak ${i + 2}: nedostaje winnerName ili tenderTitle.`);
      continue;
    }

    const rawValue = idx("value") >= 0 ? (r[idx("value")] || "").replace(",", ".").trim() : "";
    const value = rawValue ? Number(rawValue) : null;
    const rawDate = idx("awardDate") >= 0 ? (r[idx("awardDate")] || "").trim() : "";
    const awardDate = rawDate ? new Date(rawDate) : null;

    await prisma.competitorAward.create({
      data: {
        winnerName,
        tenderTitle,
        competitorId: competitorByName.get(winnerName.toLowerCase()) ?? null,
        authority: idx("authority") >= 0 ? (r[idx("authority")] || "").trim() || null : null,
        cpv: idx("cpv") >= 0 ? (r[idx("cpv")] || "").trim() || null : null,
        value: value !== null && !Number.isNaN(value) ? value : null,
        currency: idx("currency") >= 0 && r[idx("currency")]?.trim() ? r[idx("currency")].trim() : "EUR",
        awardDate: awardDate && !Number.isNaN(awardDate.getTime()) ? awardDate : null,
        productsText: idx("productsText") >= 0 ? (r[idx("productsText")] || "").trim() || null : null,
        sourceType: "manual",
        sourceUrl: idx("sourceUrl") >= 0 ? (r[idx("sourceUrl")] || "").trim() || null : null,
      },
    });
    imported++;
  }

  return NextResponse.json({ imported, errors });
}
