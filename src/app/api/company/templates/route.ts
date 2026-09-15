import { NextRequest, NextResponse } from "next/server";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { prisma } from "@/lib/db";
import { extractText } from "@/lib/extractText";
import { getOrCreateCompanyProfile } from "@/lib/companyProfile";

const UPLOAD_ROOT = path.join(process.cwd(), "uploads", "company-templates");

export async function POST(req: NextRequest) {
  const profile = await getOrCreateCompanyProfile();
  const formData = await req.formData();
  const file = formData.get("file");
  const title = typeof formData.get("title") === "string" ? (formData.get("title") as string) : "";

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
      { error: err instanceof Error ? err.message : "Greška pri čitanju predloška." },
      { status: 400 },
    );
  }

  await mkdir(UPLOAD_ROOT, { recursive: true });
  const storedName = `${randomUUID()}-${file.name}`;
  const storedPath = path.join(UPLOAD_ROOT, storedName);
  await writeFile(storedPath, buffer);

  const template = await prisma.companyTemplate.create({
    data: {
      companyProfileId: profile.id,
      title: title.trim() || file.name,
      originalName: file.name,
      storedPath,
      mimeType: file.type || "application/octet-stream",
      extractedText,
    },
  });

  return NextResponse.json({ template: { ...template, extractedText: undefined } }, { status: 201 });
}
