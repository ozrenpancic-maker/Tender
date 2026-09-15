import { NextRequest, NextResponse } from "next/server";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { prisma } from "@/lib/db";
import { extractText } from "@/lib/extractText";

const UPLOAD_ROOT = path.join(process.cwd(), "uploads");

export async function POST(req: NextRequest, { params }: { params: { id: string } }) {
  const project = await prisma.project.findUnique({ where: { id: params.id } });
  if (!project) {
    return NextResponse.json({ error: "Projekt nije pronađen." }, { status: 404 });
  }

  const formData = await req.formData();
  const file = formData.get("file");
  const kind = formData.get("kind") === "own" ? "own" : "tender";

  if (!(file instanceof File)) {
    return NextResponse.json({ error: "Nedostaje datoteka." }, { status: 400 });
  }

  const arrayBuffer = await file.arrayBuffer();
  const buffer = Buffer.from(arrayBuffer);

  let extractedText = "";
  try {
    extractedText = await extractText(buffer, file.name);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Greška pri čitanju dokumenta." },
      { status: 400 },
    );
  }

  const projectDir = path.join(UPLOAD_ROOT, project.id);
  await mkdir(projectDir, { recursive: true });
  const storedName = `${randomUUID()}-${file.name}`;
  const storedPath = path.join(projectDir, storedName);
  await writeFile(storedPath, buffer);

  const document = await prisma.document.create({
    data: {
      projectId: project.id,
      kind,
      originalName: file.name,
      storedPath,
      mimeType: file.type || "application/octet-stream",
      extractedText,
    },
  });

  return NextResponse.json({ document: { ...document, extractedText: undefined } }, { status: 201 });
}
