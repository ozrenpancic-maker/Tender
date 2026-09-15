import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { analyzeTenderDocuments } from "@/lib/analyze";

export async function POST(_req: NextRequest, { params }: { params: { id: string } }) {
  const project = await prisma.project.findUnique({
    where: { id: params.id },
    include: { documents: true },
  });

  if (!project) {
    return NextResponse.json({ error: "Projekt nije pronađen." }, { status: 404 });
  }

  const tenderDocs = project.documents.filter((d) => d.kind === "tender" && d.extractedText);
  if (tenderDocs.length === 0) {
    return NextResponse.json(
      { error: "Prvo učitaj barem jedan dokument natječajne dokumentacije." },
      { status: 400 },
    );
  }

  const combinedText = tenderDocs
    .map((d) => `\n\n===== DOKUMENT: ${d.originalName} =====\n${d.extractedText}`)
    .join("\n");

  await prisma.project.update({ where: { id: project.id }, data: { status: "analyzing" } });

  let result;
  try {
    result = await analyzeTenderDocuments(combinedText);
  } catch (err) {
    await prisma.project.update({ where: { id: project.id }, data: { status: "draft" } });
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Analiza nije uspjela." },
      { status: 500 },
    );
  }

  const { parsed, raw } = result;

  await prisma.$transaction([
    prisma.checklistItem.deleteMany({ where: { projectId: project.id } }),
    prisma.requirement.deleteMany({ where: { projectId: project.id } }),
    prisma.analysis.create({
      data: { projectId: project.id, summary: parsed.summary ?? "", rawResponse: raw },
    }),
    ...(parsed.checklist ?? []).map((item) =>
      prisma.checklistItem.create({
        data: {
          projectId: project.id,
          title: item.title,
          description: item.description ?? null,
          category: item.category ?? "ostalo",
          mandatory: item.mandatory ?? true,
        },
      }),
    ),
    ...(parsed.requirements ?? []).map((req) =>
      prisma.requirement.create({
        data: { projectId: project.id, label: req.label, value: req.value },
      }),
    ),
    prisma.project.update({ where: { id: project.id }, data: { status: "ready" } }),
  ]);

  const updated = await prisma.project.findUnique({
    where: { id: project.id },
    include: { documents: true, checklistItems: true, requirements: true, analyses: true },
  });

  return NextResponse.json({ project: updated });
}
