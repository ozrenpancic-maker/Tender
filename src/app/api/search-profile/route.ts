import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { getOrCreateSearchProfile } from "@/lib/searchProfile";

export async function GET() {
  const profile = await getOrCreateSearchProfile();
  return NextResponse.json({ profile });
}

export async function PUT(req: NextRequest) {
  const profile = await getOrCreateSearchProfile();
  const body = await req.json();

  const updated = await prisma.searchProfile.update({
    where: { id: profile.id },
    data: {
      cpvCodes: typeof body.cpvCodes === "string" ? body.cpvCodes.trim() || null : profile.cpvCodes,
      keywords: typeof body.keywords === "string" ? body.keywords.trim() || null : profile.keywords,
      minValue: body.minValue !== undefined ? (body.minValue === null ? null : Number(body.minValue)) : profile.minValue,
      maxValue: body.maxValue !== undefined ? (body.maxValue === null ? null : Number(body.maxValue)) : profile.maxValue,
      county: typeof body.county === "string" ? body.county.trim() || null : profile.county,
      sourceTed: typeof body.sourceTed === "boolean" ? body.sourceTed : profile.sourceTed,
      sourceEojn: typeof body.sourceEojn === "boolean" ? body.sourceEojn : profile.sourceEojn,
    },
  });

  return NextResponse.json({ profile: updated });
}

export const dynamic = "force-dynamic";
