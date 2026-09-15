import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export async function GET(_req: NextRequest, { params }: { params: { id: string } }) {
  const project = await prisma.project.findUnique({
    where: { id: params.id },
    include: {
      documents: { orderBy: { createdAt: "asc" } },
      checklistItems: { orderBy: { createdAt: "asc" } },
      requirements: { orderBy: { createdAt: "asc" } },
      analyses: { orderBy: { createdAt: "desc" }, take: 1 },
      generatedOffers: { orderBy: { createdAt: "desc" } },
    },
  });

  if (!project) {
    return NextResponse.json({ error: "Projekt nije pronađen." }, { status: 404 });
  }

  return NextResponse.json({ project });
}

export async function DELETE(_req: NextRequest, { params }: { params: { id: string } }) {
  await prisma.project.delete({ where: { id: params.id } });
  return NextResponse.json({ ok: true });
}

export const dynamic = "force-dynamic";
