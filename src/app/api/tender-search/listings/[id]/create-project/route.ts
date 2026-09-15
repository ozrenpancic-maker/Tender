import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export async function POST(_req: NextRequest, { params }: { params: { id: string } }) {
  const listing = await prisma.tenderListing.findUnique({ where: { id: params.id } });
  if (!listing) {
    return NextResponse.json({ error: "Natječaj nije pronađen." }, { status: 404 });
  }

  if (listing.projectId) {
    return NextResponse.json({ projectId: listing.projectId });
  }

  const project = await prisma.project.create({
    data: {
      name: listing.title,
      authority: listing.authority,
      deadline: listing.deadline,
      notes: listing.url ? `Izvor: ${listing.source.toUpperCase()} — ${listing.url}` : null,
    },
  });

  await prisma.tenderListing.update({ where: { id: listing.id }, data: { projectId: project.id } });

  return NextResponse.json({ projectId: project.id }, { status: 201 });
}
