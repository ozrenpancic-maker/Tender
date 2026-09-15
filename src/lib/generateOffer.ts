import Anthropic from "@anthropic-ai/sdk";
import { Document as DocxDocument, Packer, Paragraph, HeadingLevel, TextRun } from "docx";

const MODEL = process.env.ANTHROPIC_MODEL || "claude-sonnet-5";
const MAX_INPUT_CHARS = 150_000;

export interface OfferDraft {
  title: string;
  sections: { heading: string; content: string }[];
}

const SYSTEM_PROMPT = `Ti si stručni asistent za javnu nabavu u Hrvatskoj/EU. Na temelju sažetka natječaja,
ključnih zahtjeva, checkliste dokumenata te podataka i predložaka tvrtke ponuditelja, sastavljaš NACRT
tekstualnog dijela ponude (uvodno pismo, izjava o sposobnosti, tehnički opis, izjave sukladnosti i sl.) -
NE popunjavaš službene obrasce naručitelja niti troškovnik s cijenama koje ne znaš.

Piši hrvatskim jezikom, formalnim poslovnim stilom. Gdje podatak nedostaje, jasno napiši
"[DOPUNITI: ...]" umjesto da izmišljaš brojke, cijene, datume ili činjenice o tvrtki.

Odgovori isključivo jednim JSON objektom, bez markdown ograda, točno ovog oblika:
{
  "title": string,
  "sections": [{ "heading": string, "content": string }]
}

Uključi barem sekcije: "Uvodno pismo", "Izjava o ispunjavanju uvjeta sposobnosti", "Tehnički opis ponude",
"Napomene i dokumenti koje je potrebno priložiti" (u zadnjoj nabroji sve iz checkliste koje AI ne može sam
generirati, npr. izvadak iz registra, bankovna jamstva).`;

export async function draftOffer(params: {
  projectSummary: string;
  requirements: { label: string; value: string }[];
  checklist: { title: string; description: string | null; mandatory: boolean }[];
  companyName: string;
  companyDescription: string | null;
  companyDetails: string;
  templateExcerpts: { title: string; text: string }[];
}): Promise<{ parsed: OfferDraft; raw: string }> {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    throw new Error("ANTHROPIC_API_KEY nije postavljen. Dodaj ga u .env datoteku.");
  }

  const client = new Anthropic({ apiKey });

  const templatesText = params.templateExcerpts
    .map((t) => `\n--- Predložak tvrtke: ${t.title} ---\n${t.text.slice(0, 8000)}`)
    .join("\n");

  const userContent = `
SAŽETAK NATJEČAJA:
${params.projectSummary}

KLJUČNI ZAHTJEVI:
${params.requirements.map((r) => `- ${r.label}: ${r.value}`).join("\n") || "(nema izvučenih zahtjeva)"}

CHECKLIST DOKUMENATA ZA PONUDU:
${
  params.checklist
    .map((c) => `- ${c.title}${c.mandatory ? " (obavezno)" : ""}${c.description ? " — " + c.description : ""}`)
    .join("\n") || "(nema)"
}

PODACI O TVRTKI PONUDITELJA:
Naziv: ${params.companyName}
${params.companyDetails}
Opis/reference: ${params.companyDescription ?? "(nije uneseno)"}

VLASTITI PREDLOŠCI TVRTKE (koristi ih kao stilski i sadržajni referentni okvir):
${templatesText || "(nema učitanih predložaka)"}
`.slice(0, MAX_INPUT_CHARS);

  const message = await client.messages.create({
    model: MODEL,
    max_tokens: 4096,
    system: SYSTEM_PROMPT,
    messages: [{ role: "user", content: userContent }],
  });

  const textBlock = message.content.find((block) => block.type === "text");
  const raw = textBlock && "text" in textBlock ? textBlock.text : "";

  let parsed: OfferDraft;
  try {
    parsed = JSON.parse(raw);
  } catch {
    const match = raw.match(/\{[\s\S]*\}/);
    if (!match) throw new Error("AI odgovor nije bilo moguće protumačiti kao JSON.");
    parsed = JSON.parse(match[0]);
  }

  return { parsed, raw };
}

export async function buildOfferDocx(draft: OfferDraft): Promise<Buffer> {
  const children: Paragraph[] = [
    new Paragraph({ text: draft.title, heading: HeadingLevel.TITLE }),
  ];

  for (const section of draft.sections) {
    children.push(new Paragraph({ text: section.heading, heading: HeadingLevel.HEADING_1 }));
    for (const line of section.content.split(/\n+/)) {
      if (!line.trim()) continue;
      children.push(
        new Paragraph({
          children: [new TextRun(line.trim())],
        }),
      );
    }
  }

  const doc = new DocxDocument({ sections: [{ children }] });
  return Packer.toBuffer(doc);
}
