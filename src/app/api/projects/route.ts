import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export async function GET() {
  const projects = await prisma.project.findMany({
    orderBy: { createdAt: "desc" },
    include: {
      _count: { select: { documents: true, checklistItems: true } },
    },
  });
  return NextResponse.json({ projects });
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  const name = typeof body.name === "string" ? body.name.trim() : "";

  if (!name) {
    return NextResponse.json({ error: "Naziv projekta je obavezan." }, { status: 400 });
  }

  const project = await prisma.project.create({
    data: {
      name,
      authority: typeof body.authority === "string" ? body.authority.trim() || null : null,
    },
  });

  return NextResponse.json({ project }, { status: 201 });
}

export const dynamic = "force-dynamic";
