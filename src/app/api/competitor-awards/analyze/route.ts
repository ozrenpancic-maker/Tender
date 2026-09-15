import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { analyzeCompetitorAwards } from "@/lib/analyzeCompetitors";
import type { Prisma } from "@prisma/client";

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));

  const where: Prisma.CompetitorAwardWhereInput = {};
  if (body.competitorId) where.competitorId = body.competitorId;
  if (body.cpv) where.cpv = { contains: body.cpv };
  if (body.q) {
    where.OR = [
      { tenderTitle: { contains: body.q } },
      { winnerName: { contains: body.q } },
      { productsText: { contains: body.q } },
      { authority: { contains: body.q } },
    ];
  }

  const awards = await prisma.competitorAward.findMany({
    where,
    orderBy: { awardDate: "desc" },
    take: 300,
  });

  try {
    const analysis = await analyzeCompetitorAwards(
      awards.map((a) => ({
        winnerName: a.winnerName,
        authority: a.authority,
        cpv: a.cpv,
        tenderTitle: a.tenderTitle,
        value: a.value,
        currency: a.currency,
        awardDate: a.awardDate ? a.awardDate.toISOString().slice(0, 10) : null,
        productsText: a.productsText,
      })),
    );
    return NextResponse.json({ analysis, count: awards.length });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Analiza nije uspjela." },
      { status: 500 },
    );
  }
}
