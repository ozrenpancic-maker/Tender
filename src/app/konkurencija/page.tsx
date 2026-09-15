import { prisma } from "@/lib/db";
import CompetitorsWorkspace from "@/components/CompetitorsWorkspace";

export default async function CompetitorsPage() {
  const [competitors, awards] = await Promise.all([
    prisma.competitor.findMany({ orderBy: { name: "asc" }, include: { _count: { select: { awards: true } } } }),
    prisma.competitorAward.findMany({ orderBy: { awardDate: "desc" }, include: { competitor: true }, take: 200 }),
  ]);

  return <CompetitorsWorkspace initialCompetitors={competitors} initialAwards={awards} />;
}

export const dynamic = "force-dynamic";
