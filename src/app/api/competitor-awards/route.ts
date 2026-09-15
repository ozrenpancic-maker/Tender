import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import type { Prisma } from "@prisma/client";

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const competitorId = searchParams.get("competitorId");
  const cpv = searchParams.get("cpv");
  const q = searchParams.get("q");

  const where: Prisma.CompetitorAwardWhereInput = {};
  if (competitorId) where.competitorId = competitorId;
  if (cpv) where.cpv = { contains: cpv };
  if (q) {
    where.OR = [
      { tenderTitle: { contains: q } },
      { winnerName: { contains: q } },
      { productsText: { contains: q } },
      { authority: { contains: q } },
    ];
  }

  const awards = await prisma.competitorAward.findMany({
    where,
    orderBy: { awardDate: "desc" },
    include: { competitor: true },
    take: 500,
  });

  return NextResponse.json({ awards });
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  const winnerName = typeof body.winnerName === "string" ? body.winnerName.trim() : "";
  const tenderTitle = typeof body.tenderTitle === "string" ? body.tenderTitle.trim() : "";

  if (!winnerName || !tenderTitle) {
    return NextResponse.json({ error: "Naziv pobjednika i naziv natječaja su obavezni." }, { status: 400 });
  }

  const award = await prisma.competitorAward.create({
    data: {
      winnerName,
      tenderTitle,
      competitorId: typeof body.competitorId === "string" && body.competitorId ? body.competitorId : null,
      authority: typeof body.authority === "string" ? body.authority.trim() || null : null,
      cpv: typeof body.cpv === "string" ? body.cpv.trim() || null : null,
      value: typeof body.value === "number" ? body.value : body.value ? Number(body.value) : null,
      currency: typeof body.currency === "string" && body.currency ? body.currency : "EUR",
      awardDate: body.awardDate ? new Date(body.awardDate) : null,
      productsText: typeof body.productsText === "string" ? body.productsText.trim() || null : null,
      sourceType: "manual",
      sourceUrl: typeof body.sourceUrl === "string" ? body.sourceUrl.trim() || null : null,
    },
  });

  return NextResponse.json({ award }, { status: 201 });
}

export const dynamic = "force-dynamic";
