import path from "node:path";

// Izvlači tekstualni sadržaj iz uploadanog dokumenta (PDF ili DOCX) radi AI analize.
export async function extractText(buffer: Buffer, originalName: string): Promise<string> {
  const ext = path.extname(originalName).toLowerCase();

  if (ext === ".pdf") {
    const pdfParse = (await import("pdf-parse")).default;
    const result = await pdfParse(buffer);
    return result.text;
  }

  if (ext === ".docx") {
    const mammoth = await import("mammoth");
    const result = await mammoth.extractRawText({ buffer });
    return result.value;
  }

  if (ext === ".txt") {
    return buffer.toString("utf-8");
  }

  throw new Error(`Nepodržani format datoteke: ${ext || "nepoznat"}. Podržani su PDF, DOCX i TXT.`);
}
