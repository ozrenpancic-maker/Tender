import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export async function GET() {
  const competitors = await prisma.competitor.findMany({
    orderBy: { name: "asc" },
    include: { _count: { select: { awards: true } } },
  });
  return NextResponse.json({ competitors });
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  const name = typeof body.name === "string" ? body.name.trim() : "";

  if (!name) {
    return NextResponse.json({ error: "Naziv konkurenta je obavezan." }, { status: 400 });
  }

  try {
    const competitor = await prisma.competitor.create({
      data: { name, notes: typeof body.notes === "string" ? body.notes.trim() || null : null },
    });
    return NextResponse.json({ competitor }, { status: 201 });
  } catch {
    return NextResponse.json({ error: "Konkurent s tim nazivom već postoji." }, { status: 409 });
  }
}

export const dynamic = "force-dynamic";
