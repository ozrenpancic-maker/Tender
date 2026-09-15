import Anthropic from "@anthropic-ai/sdk";

const MODEL = process.env.ANTHROPIC_MODEL || "claude-sonnet-5";
const MAX_INPUT_CHARS = 180_000; // grubo ograničenje da ostanemo unutar context prozora

export interface AnalysisResult {
  summary: string;
  requirements: { label: string; value: string }[];
  checklist: {
    title: string;
    description?: string;
    category: "pravni" | "financijski" | "tehnicki" | "obrazac" | "ostalo";
    mandatory: boolean;
  }[];
}

const SYSTEM_PROMPT = `Ti si stručni asistent za javnu nabavu u Hrvatskoj/EU. Analiziraš natječajnu dokumentaciju
(poziv na nadmetanje, troškovnik, uvjete sposobnosti, obrasce) i korisniku - ponuditelju - pripremaš:
1) sažetak natječaja,
2) popis ključnih zahtjeva (rokovi, procijenjena vrijednost, kriterij odabira, jamstva, uvjeti sposobnosti),
3) checklist svih dokumenata/priloga koje ponuditelj mora pripremiti i predati uz ponudu.

Odgovaraj isključivo hrvatskim jezikom i isključivo jednim JSON objektom, bez markdown ograda, bez dodatnog teksta,
točno ovog oblika:
{
  "summary": string,
  "requirements": [{ "label": string, "value": string }],
  "checklist": [{ "title": string, "description": string, "category": "pravni"|"financijski"|"tehnicki"|"obrazac"|"ostalo", "mandatory": boolean }]
}

Ako neki podatak nije naveden u dokumentaciji, izostavi ga umjesto da ga izmišljaš. Checklist neka bude konkretan
(npr. "Izvadak iz sudskog registra", "ESPD obrazac", "Jamstvo za ozbiljnost ponude", "Referenc lista", "Troškovnik - ispunjen i potpisan").`;

export async function analyzeTenderDocuments(combinedText: string): Promise<{
  parsed: AnalysisResult;
  raw: string;
}> {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    throw new Error("ANTHROPIC_API_KEY nije postavljen. Dodaj ga u .env datoteku.");
  }

  const client = new Anthropic({ apiKey });
  const truncated = combinedText.slice(0, MAX_INPUT_CHARS);

  const message = await client.messages.create({
    model: MODEL,
    max_tokens: 4096,
    system: SYSTEM_PROMPT,
    messages: [
      {
        role: "user",
        content: `Ovo je tekst izvučen iz natječajne dokumentacije (može sadržavati više dokumenata spojenih zajedno):\n\n${truncated}`,
      },
    ],
  });

  const textBlock = message.content.find((block) => block.type === "text");
  const raw = textBlock && "text" in textBlock ? textBlock.text : "";

  let parsed: AnalysisResult;
  try {
    parsed = JSON.parse(raw);
  } catch {
    const match = raw.match(/\{[\s\S]*\}/);
    if (!match) {
      throw new Error("AI odgovor nije bilo moguće protumačiti kao JSON.");
    }
    parsed = JSON.parse(match[0]);
  }

  return { parsed, raw };
}
