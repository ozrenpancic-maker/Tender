import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import type { Prisma } from "@prisma/client";

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const source = searchParams.get("source");
  const q = searchParams.get("q");

  const where: Prisma.TenderListingWhereInput = {};
  if (source) where.source = source;
  if (q) {
    where.OR = [
      { title: { contains: q } },
      { authority: { contains: q } },
      { cpv: { contains: q } },
    ];
  }

  const listings = await prisma.tenderListing.findMany({
    where,
    orderBy: { createdAt: "desc" },
    take: 200,
  });

  return NextResponse.json({ listings });
}

export const dynamic = "force-dynamic";
