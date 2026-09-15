import { NextRequest, NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import { prisma } from "@/lib/db";

export async function GET(
  _req: NextRequest,
  { params }: { params: { id: string; offerId: string } },
) {
  const offer = await prisma.generatedOffer.findFirst({
    where: { id: params.offerId, projectId: params.id },
  });

  if (!offer) {
    return NextResponse.json({ error: "Nacrt ponude nije pronađen." }, { status: 404 });
  }

  const buffer = await readFile(offer.storedPath);

  return new NextResponse(buffer, {
    headers: {
      "Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "Content-Disposition": `attachment; filename="${offer.originalName}"`,
    },
  });
}

export const dynamic = "force-dynamic";
