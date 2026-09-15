"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

interface DocumentDto {
  id: string;
  kind: string;
  originalName: string;
  createdAt: string | Date;
}

interface ChecklistItemDto {
  id: string;
  title: string;
  description: string | null;
  category: string;
  mandatory: boolean;
  fulfilled: boolean;
}

interface RequirementDto {
  id: string;
  label: string;
  value: string;
}

interface AnalysisDto {
  id: string;
  summary: string;
}

interface GeneratedOfferDto {
  id: string;
  originalName: string;
  createdAt: string | Date;
}

interface ProjectDto {
  id: string;
  name: string;
  authority: string | null;
  status: string;
  documents: DocumentDto[];
  checklistItems: ChecklistItemDto[];
  requirements: RequirementDto[];
  analyses: AnalysisDto[];
  generatedOffers: GeneratedOfferDto[];
}

const CATEGORY_LABEL: Record<string, string> = {
  pravni: "Pravni dokumenti",
  financijski: "Financijski dokumenti",
  tehnicki: "Tehnička dokumentacija",
  obrazac: "Obrasci",
  ostalo: "Ostalo",
};

export default function ProjectWorkspace({ project }: { project: ProjectDto }) {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState<"tender" | "own">("tender");
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [generatingOffer, setGeneratingOffer] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const tenderDocs = project.documents.filter((d) => d.kind === "tender");
  const ownDocs = project.documents.filter((d) => d.kind === "own");
  const latestSummary = project.analyses[0]?.summary;

  const grouped = project.checklistItems.reduce<Record<string, ChecklistItemDto[]>>((acc, item) => {
    acc[item.category] = acc[item.category] || [];
    acc[item.category].push(item);
    return acc;
  }, {});

  async function handleUpload() {
    const file = fileInputRef.current?.files?.[0];
    if (!file) return;

    setUploading(true);
    setError(null);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("kind", kind);

    const res = await fetch(`/api/projects/${project.id}/documents`, {
      method: "POST",
      body: formData,
    });

    setUploading(false);

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      setError(data.error || "Upload nije uspio.");
      return;
    }

    if (fileInputRef.current) fileInputRef.current.value = "";
    router.refresh();
  }

  async function handleAnalyze() {
    setAnalyzing(true);
    setError(null);

    const res = await fetch(`/api/projects/${project.id}/analyze`, { method: "POST" });

    setAnalyzing(false);

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      setError(data.error || "Analiza nije uspjela.");
      return;
    }

    router.refresh();
  }

  async function handleGenerateOffer() {
    setGeneratingOffer(true);
    setError(null);

    const res = await fetch(`/api/projects/${project.id}/offer`, { method: "POST" });

    setGeneratingOffer(false);

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      setError(data.error || "Generiranje nacrta ponude nije uspjelo.");
      return;
    }

    router.refresh();
  }

  async function toggleItem(item: ChecklistItemDto) {
    await fetch(`/api/projects/${project.id}/checklist/${item.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fulfilled: !item.fulfilled }),
    });
    router.refresh();
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">{project.name}</h1>
        <p className="text-sm text-slate-500">{project.authority || "Naručitelj nije naveden"}</p>
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      <section className="rounded-lg border border-slate-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-medium">1. Učitaj dokumentaciju</h2>
        <div className="flex flex-wrap items-center gap-3">
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value as "tender" | "own")}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="tender">Natječajna dokumentacija</option>
            <option value="own">Vlastiti dokument tvrtke</option>
          </select>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.txt"
            className="text-sm"
          />
          <button
            onClick={handleUpload}
            disabled={uploading}
            className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {uploading ? "Učitavam…" : "Učitaj"}
          </button>
        </div>

        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <div>
            <h3 className="mb-2 text-sm font-medium text-slate-600">Natječajna dokumentacija</h3>
            {tenderDocs.length === 0 ? (
              <p className="text-sm text-slate-400">Nema učitanih dokumenata.</p>
            ) : (
              <ul className="space-y-1 text-sm">
                {tenderDocs.map((d) => (
                  <li key={d.id} className="truncate">
                    📄 {d.originalName}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <h3 className="mb-2 text-sm font-medium text-slate-600">Vlastiti dokumenti tvrtke</h3>
            {ownDocs.length === 0 ? (
              <p className="text-sm text-slate-400">Nema učitanih dokumenata.</p>
            ) : (
              <ul className="space-y-1 text-sm">
                {ownDocs.map((d) => (
                  <li key={d.id} className="truncate">
                    📄 {d.originalName}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-6">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-medium">2. Analiziraj dokumentaciju</h2>
          <button
            onClick={handleAnalyze}
            disabled={analyzing || tenderDocs.length === 0}
            className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {analyzing ? "Analiziram…" : "Pokreni AI analizu"}
          </button>
        </div>
        {tenderDocs.length === 0 && (
          <p className="mt-2 text-sm text-slate-400">Prvo učitaj barem jedan dokument natječajne dokumentacije.</p>
        )}
        {latestSummary && <p className="mt-4 whitespace-pre-line text-sm text-slate-700">{latestSummary}</p>}
      </section>

      {project.requirements.length > 0 && (
        <section className="rounded-lg border border-slate-200 bg-white p-6">
          <h2 className="mb-4 text-lg font-medium">Ključni zahtjevi natječaja</h2>
          <dl className="grid gap-3 sm:grid-cols-2">
            {project.requirements.map((r) => (
              <div key={r.id} className="rounded-md bg-slate-50 p-3">
                <dt className="text-xs font-medium uppercase text-slate-500">{r.label}</dt>
                <dd className="text-sm text-slate-800">{r.value}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      {project.checklistItems.length > 0 && (
        <section className="rounded-lg border border-slate-200 bg-white p-6">
          <h2 className="mb-4 text-lg font-medium">3. Checklist dokumenata za ponudu</h2>
          <div className="space-y-6">
            {Object.entries(grouped).map(([category, items]) => (
              <div key={category}>
                <h3 className="mb-2 text-sm font-semibold text-slate-600">
                  {CATEGORY_LABEL[category] ?? category}
                </h3>
                <ul className="space-y-2">
                  {items.map((item) => (
                    <li key={item.id} className="flex items-start gap-3 rounded-md border border-slate-100 p-3">
                      <input
                        type="checkbox"
                        checked={item.fulfilled}
                        onChange={() => toggleItem(item)}
                        className="mt-1 h-4 w-4 accent-brand-600"
                      />
                      <div>
                        <p className={item.fulfilled ? "text-sm font-medium line-through text-slate-400" : "text-sm font-medium"}>
                          {item.title}
                          {item.mandatory && <span className="ml-2 text-xs text-red-500">obavezno</span>}
                        </p>
                        {item.description && <p className="text-sm text-slate-500">{item.description}</p>}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="rounded-lg border border-slate-200 bg-white p-6">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-medium">4. Nacrt ponude</h2>
          <button
            onClick={handleGenerateOffer}
            disabled={generatingOffer || project.analyses.length === 0}
            className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {generatingOffer ? "Sastavljam…" : "Generiraj nacrt ponude (.docx)"}
          </button>
        </div>
        {project.analyses.length === 0 && (
          <p className="mt-2 text-sm text-slate-400">Prvo pokreni AI analizu dokumentacije (korak 2).</p>
        )}
        <p className="mt-2 text-sm text-slate-500">
          AI sastavlja tekstualni dio ponude (uvodno pismo, izjave, tehnički opis) na temelju profila tvrtke i
          njenih predložaka. Ovo je nacrt za tvoju provjeru i dopunu — ne popunjava službene obrasce naručitelja
          niti izmišlja cijene ili činjenice.{" "}
          <a href="/company" className="text-brand-600 hover:underline">
            Uredi profil tvrtke i predloške →
          </a>
        </p>
        {project.generatedOffers.length > 0 && (
          <ul className="mt-4 space-y-1 text-sm">
            {project.generatedOffers.map((o) => (
              <li key={o.id}>
                📄{" "}
                <a
                  href={`/api/projects/${project.id}/offer/${o.id}/download`}
                  className="text-brand-600 hover:underline"
                >
                  {o.originalName}
                </a>{" "}
                <span className="text-slate-400">
                  ({new Date(o.createdAt).toLocaleString("hr-HR")})
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
