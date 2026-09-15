import { NextRequest, NextResponse } from "next/server";
import { unlink } from "node:fs/promises";
import { prisma } from "@/lib/db";

export async function DELETE(_req: NextRequest, { params }: { params: { id: string } }) {
  const template = await prisma.companyTemplate.findUnique({ where: { id: params.id } });
  if (!template) {
    return NextResponse.json({ error: "Predložak nije pronađen." }, { status: 404 });
  }

  await prisma.companyTemplate.delete({ where: { id: params.id } });
  await unlink(template.storedPath).catch(() => {});

  return NextResponse.json({ ok: true });
}
