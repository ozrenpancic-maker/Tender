import { NextRequest, NextResponse } from "next/server";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { prisma } from "@/lib/db";
import { draftOffer, buildOfferDocx } from "@/lib/generateOffer";
import { getOrCreateCompanyProfile } from "@/lib/companyProfile";

const UPLOAD_ROOT = path.join(process.cwd(), "uploads");

export async function POST(_req: NextRequest, { params }: { params: { id: string } }) {
  const project = await prisma.project.findUnique({
    where: { id: params.id },
    include: { requirements: true, checklistItems: true, analyses: { orderBy: { createdAt: "desc" }, take: 1 } },
  });

  if (!project) {
    return NextResponse.json({ error: "Projekt nije pronađen." }, { status: 404 });
  }

  if (!project.analyses[0]) {
    return NextResponse.json(
      { error: "Prvo pokreni AI analizu natječajne dokumentacije (korak 2)." },
      { status: 400 },
    );
  }

  const companyProfile = await prisma.companyProfile.findFirst({ include: { templates: true } });
  if (!companyProfile) {
    return NextResponse.json(
      { error: "Prvo popuni profil tvrtke na stranici /company." },
      { status: 400 },
    );
  }

  const companyDetails = [
    companyProfile.oib ? `OIB: ${companyProfile.oib}` : null,
    companyProfile.address ? `Adresa: ${companyProfile.address}` : null,
    companyProfile.iban ? `IBAN: ${companyProfile.iban}` : null,
    companyProfile.contactEmail ? `E-mail: ${companyProfile.contactEmail}` : null,
    companyProfile.contactPhone ? `Telefon: ${companyProfile.contactPhone}` : null,
  ]
    .filter(Boolean)
    .join("\n");

  let result;
  try {
    result = await draftOffer({
      projectSummary: project.analyses[0].summary,
      requirements: project.requirements.map((r) => ({ label: r.label, value: r.value })),
      checklist: project.checklistItems.map((c) => ({
        title: c.title,
        description: c.description,
        mandatory: c.mandatory,
      })),
      companyName: companyProfile.name,
      companyDescription: companyProfile.description,
      companyDetails,
      templateExcerpts: companyProfile.templates
        .filter((t) => t.extractedText)
        .map((t) => ({ title: t.title, text: t.extractedText || "" })),
    });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Generiranje nacrta ponude nije uspjelo." },
      { status: 500 },
    );
  }

  const buffer = await buildOfferDocx(result.parsed);

  const projectDir = path.join(UPLOAD_ROOT, project.id, "offers");
  await mkdir(projectDir, { recursive: true });
  const fileName = `Nacrt-ponude-${randomUUID()}.docx`;
  const storedPath = path.join(projectDir, fileName);
  await writeFile(storedPath, buffer);

  const offer = await prisma.generatedOffer.create({
    data: { projectId: project.id, originalName: fileName, storedPath },
  });

  return NextResponse.json({ offer }, { status: 201 });
}
