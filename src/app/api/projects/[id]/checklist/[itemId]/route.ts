import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export async function PATCH(
  req: NextRequest,
  { params }: { params: { id: string; itemId: string } },
) {
  const body = await req.json();

  const item = await prisma.checklistItem.update({
    where: { id: params.itemId },
    data: { fulfilled: Boolean(body.fulfilled) },
  });

  return NextResponse.json({ item });
}
