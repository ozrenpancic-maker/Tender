import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { getOrCreateCompanyProfile } from "@/lib/companyProfile";

export async function GET() {
  const profile = await getOrCreateCompanyProfile();
  const withTemplates = await prisma.companyProfile.findUnique({
    where: { id: profile.id },
    include: { templates: { orderBy: { createdAt: "asc" } } },
  });
  return NextResponse.json({ profile: withTemplates });
}

export async function PUT(req: NextRequest) {
  const profile = await getOrCreateCompanyProfile();
  const body = await req.json();

  const updated = await prisma.companyProfile.update({
    where: { id: profile.id },
    data: {
      name: typeof body.name === "string" && body.name.trim() ? body.name.trim() : profile.name,
      oib: typeof body.oib === "string" ? body.oib.trim() || null : profile.oib,
      address: typeof body.address === "string" ? body.address.trim() || null : profile.address,
      contactEmail:
        typeof body.contactEmail === "string" ? body.contactEmail.trim() || null : profile.contactEmail,
      contactPhone:
        typeof body.contactPhone === "string" ? body.contactPhone.trim() || null : profile.contactPhone,
      iban: typeof body.iban === "string" ? body.iban.trim() || null : profile.iban,
      description:
        typeof body.description === "string" ? body.description.trim() || null : profile.description,
    },
  });

  return NextResponse.json({ profile: updated });
}

export const dynamic = "force-dynamic";
