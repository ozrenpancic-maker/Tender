import Anthropic from "@anthropic-ai/sdk";

const MODEL = process.env.ANTHROPIC_MODEL || "claude-sonnet-5";

const SYSTEM_PROMPT = `Ti si analitičar tržišta javne nabave. Dobivaš popis javno objavljenih dodjela ugovora
(pobjednik, naručitelj, CPV, naziv natječaja, vrijednost, datum, opis proizvoda/usluga). Na temelju toga
korisniku - ponuditelju koji razmišlja o prijavi na sličan natječaj - daješ sažetu analizu:
- raspon i prosjek cijena po sličnim stavkama/natječajima,
- koji proizvodi/usluge se najčešće pojavljuju,
- koji konkurenti dominiraju i po kojoj otprilike cjenovnoj razini,
- praktičnu preporuku kako pozicionirati vlastitu ponudu (cijena, asortiman).

Piši hrvatskim jezikom, sažeto (5-10 odlomaka/točaka), bez izmišljanja podataka koji nisu u ulaznim podacima -
ako podataka nema dovoljno za neki zaključak, jasno to reci.`;

export async function analyzeCompetitorAwards(
  awards: {
    winnerName: string;
    authority: string | null;
    cpv: string | null;
    tenderTitle: string;
    value: number | null;
    currency: string;
    awardDate: string | null;
    productsText: string | null;
  }[],
): Promise<string> {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    throw new Error("ANTHROPIC_API_KEY nije postavljen. Dodaj ga u .env datoteku.");
  }

  if (awards.length === 0) {
    throw new Error("Nema podataka o dodjelama za analizu. Prvo dodaj ili uvezi barem nekoliko zapisa.");
  }

  const client = new Anthropic({ apiKey });

  const table = awards
    .slice(0, 300)
    .map(
      (a) =>
        `- ${a.awardDate ?? "?"} | ${a.winnerName} | ${a.authority ?? "?"} | CPV ${a.cpv ?? "?"} | ${a.tenderTitle} | ${
          a.value != null ? `${a.value} ${a.currency}` : "?"
        } | ${a.productsText ?? ""}`,
    )
    .join("\n");

  const message = await client.messages.create({
    model: MODEL,
    max_tokens: 2048,
    system: SYSTEM_PROMPT,
    messages: [
      {
        role: "user",
        content: `Popis dodjela ugovora (${awards.length} zapisa):\n${table}`,
      },
    ],
  });

  const textBlock = message.content.find((block) => block.type === "text");
  return textBlock && "text" in textBlock ? textBlock.text : "";
}
