import Link from "next/link";
import { prisma } from "@/lib/db";

const STATUS_LABEL: Record<string, string> = {
  draft: "Priprema",
  analyzing: "Analiza u tijeku…",
  ready: "Checklist spreman",
  submitted: "Predano",
};

export default async function HomePage() {
  const projects = await prisma.project.findMany({
    orderBy: { createdAt: "desc" },
    include: { _count: { select: { documents: true, checklistItems: true } } },
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Moji natječaji</h1>
          <p className="text-sm text-slate-500">
            Učitaj natječajnu dokumentaciju i dobij checklistu dokumenata koje trebaš pripremiti.
          </p>
        </div>
        <Link
          href="/projects/new"
          className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
        >
          + Novi natječaj
        </Link>
      </div>

      {projects.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-300 bg-white p-10 text-center text-slate-500">
          Još nemaš dodanih natječaja. Klikni &quot;Novi natječaj&quot; za početak.
        </div>
      ) : (
        <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">
          {projects.map((p) => (
            <li key={p.id}>
              <Link
                href={`/projects/${p.id}`}
                className="flex items-center justify-between px-5 py-4 hover:bg-slate-50"
              >
                <div>
                  <p className="font-medium">{p.name}</p>
                  <p className="text-sm text-slate-500">
                    {p.authority || "Naručitelj nije naveden"} · {p._count.documents} dokumenata ·{" "}
                    {p._count.checklistItems} stavki checklista
                  </p>
                </div>
                <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
                  {STATUS_LABEL[p.status] ?? p.status}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export const dynamic = "force-dynamic";
