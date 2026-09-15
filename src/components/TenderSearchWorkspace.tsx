"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

interface ProfileDto {
  id: string;
  cpvCodes: string | null;
  keywords: string | null;
  minValue: number | null;
  maxValue: number | null;
  county: string | null;
  sourceTed: boolean;
  sourceEojn: boolean;
}

interface ListingDto {
  id: string;
  source: string;
  title: string;
  authority: string | null;
  cpv: string | null;
  deadline: string | Date | null;
  estimatedValue: number | null;
  currency: string;
  url: string | null;
  projectId: string | null;
}

interface DiagnosticSide {
  ok: boolean;
  message: string;
  sampleCount: number;
  sample: unknown[];
  debug?: { url: string; status?: number; sample?: string; error?: string };
}

export default function TenderSearchWorkspace({
  initialProfile,
  initialListings,
}: {
  initialProfile: ProfileDto;
  initialListings: ListingDto[];
}) {
  const router = useRouter();
  const [form, setForm] = useState({
    cpvCodes: initialProfile.cpvCodes ?? "",
    keywords: initialProfile.keywords ?? "",
    minValue: initialProfile.minValue?.toString() ?? "",
    maxValue: initialProfile.maxValue?.toString() ?? "",
    county: initialProfile.county ?? "",
    sourceTed: initialProfile.sourceTed,
    sourceEojn: initialProfile.sourceEojn,
  });
  const [listings, setListings] = useState(initialListings);
  const [filterSource, setFilterSource] = useState("");
  const [filterQ, setFilterQ] = useState("");

  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [diagnostics, setDiagnostics] = useState<{ ted: DiagnosticSide; eojn: DiagnosticSide } | null>(null);
  const [creatingProjectFor, setCreatingProjectFor] = useState<string | null>(null);

  async function saveProfile(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);

    const res = await fetch("/api/search-profile", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...form,
        minValue: form.minValue ? Number(form.minValue) : null,
        maxValue: form.maxValue ? Number(form.maxValue) : null,
      }),
    });

    setSaving(false);
    if (!res.ok) {
      setError("Spremanje kriterija nije uspjelo.");
      return;
    }
    setInfo("Kriteriji spremljeni.");
  }

  async function testConnection() {
    setTesting(true);
    setError(null);
    setDiagnostics(null);
    await saveProfileSilently();

    const res = await fetch("/api/tender-search/test-connection");
    setTesting(false);

    if (!res.ok) {
      setError("Testiranje veze nije uspjelo.");
      return;
    }
    const data = await res.json();
    setDiagnostics(data);
  }

  async function saveProfileSilently() {
    await fetch("/api/search-profile", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...form,
        minValue: form.minValue ? Number(form.minValue) : null,
        maxValue: form.maxValue ? Number(form.maxValue) : null,
      }),
    });
  }

  async function runSearch() {
    setRunning(true);
    setError(null);
    setInfo(null);
    await saveProfileSilently();

    const res = await fetch("/api/tender-search/run", { method: "POST" });
    setRunning(false);

    if (!res.ok) {
      setError("Pokretanje pretrage nije uspjelo.");
      return;
    }
    const data = await res.json();
    setInfo(
      `Novo: ${data.created}, ažurirano: ${data.updated}. TED: ${data.diagnostics.ted ?? "isključen"} EOJN: ${
        data.diagnostics.eojn ?? "isključen"
      }`,
    );
    refreshListings();
  }

  async function refreshListings() {
    const params = new URLSearchParams();
    if (filterSource) params.set("source", filterSource);
    if (filterQ) params.set("q", filterQ);
    const res = await fetch(`/api/tender-search/listings?${params.toString()}`);
    const data = await res.json();
    setListings(data.listings);
  }

  async function createProject(listingId: string) {
    setCreatingProjectFor(listingId);
    const res = await fetch(`/api/tender-search/listings/${listingId}/create-project`, { method: "POST" });
    setCreatingProjectFor(null);

    if (!res.ok) {
      setError("Stvaranje projekta nije uspjelo.");
      return;
    }
    const data = await res.json();
    router.push(`/projects/${data.projectId}`);
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">Pretraga natječaja</h1>
        <p className="text-sm text-slate-500">
          Automatska pretraga TED-a (EU) i EOJN RH prema tvojim kriterijima. TED koristi njihov javni API.
          EOJN RH nema poznat javni API pa se koristi scraper koji nije uživo testiran u ovom okruženju —
          prije oslanjanja na njega pokreni &quot;Testiraj vezu&quot; i po potrebi javi ako vraća pogrešne
          podatke.
        </p>
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}
      {info && (
        <div className="rounded-md border border-brand-100 bg-brand-50 px-4 py-3 text-sm text-brand-700">{info}</div>
      )}

      <section className="rounded-lg border border-slate-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-medium">Kriteriji pretrage</h2>
        <form onSubmit={saveProfile} className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">CPV kodovi (odvojeni zarezom)</label>
            <input
              value={form.cpvCodes}
              onChange={(e) => setForm((f) => ({ ...f, cpvCodes: e.target.value }))}
              placeholder="30190000, 79800000"
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Ključne riječi (odvojene zarezom)</label>
            <input
              value={form.keywords}
              onChange={(e) => setForm((f) => ({ ...f, keywords: e.target.value }))}
              placeholder="uredski materijal, tisak"
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Min. vrijednost (EUR)</label>
            <input
              type="number"
              value={form.minValue}
              onChange={(e) => setForm((f) => ({ ...f, minValue: e.target.value }))}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Maks. vrijednost (EUR)</label>
            <input
              type="number"
              value={form.maxValue}
              onChange={(e) => setForm((f) => ({ ...f, maxValue: e.target.value }))}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Županija / regija</label>
            <input
              value={form.county}
              onChange={(e) => setForm((f) => ({ ...f, county: e.target.value }))}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
          <div className="flex items-end gap-4">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.sourceTed}
                onChange={(e) => setForm((f) => ({ ...f, sourceTed: e.target.checked }))}
                className="h-4 w-4 accent-brand-600"
              />
              TED (EU)
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.sourceEojn}
                onChange={(e) => setForm((f) => ({ ...f, sourceEojn: e.target.checked }))}
                className="h-4 w-4 accent-brand-600"
              />
              EOJN RH
            </label>
          </div>
          <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
            <button
              type="submit"
              disabled={saving}
              className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
            >
              {saving ? "Spremam…" : "Spremi kriterije"}
            </button>
            <button
              type="button"
              onClick={testConnection}
              disabled={testing}
              className="rounded-md border border-slate-300 px-4 py-2 text-sm hover:bg-slate-50 disabled:opacity-50"
            >
              {testing ? "Testiram…" : "Testiraj vezu"}
            </button>
            <button
              type="button"
              onClick={runSearch}
              disabled={running}
              className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
            >
              {running ? "Pretražujem…" : "Pokreni pretragu"}
            </button>
          </div>
        </form>

        {diagnostics && (
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            <DiagnosticCard title="TED" data={diagnostics.ted} />
            <DiagnosticCard title="EOJN RH" data={diagnostics.eojn} />
          </div>
        )}
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-medium">Pronađeni natječaji</h2>
          <div className="flex gap-2">
            <select
              value={filterSource}
              onChange={(e) => setFilterSource(e.target.value)}
              className="rounded-md border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="">Svi izvori</option>
              <option value="ted">TED</option>
              <option value="eojn">EOJN RH</option>
            </select>
            <input
              placeholder="Pretraga…"
              value={filterQ}
              onChange={(e) => setFilterQ(e.target.value)}
              className="rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
            <button
              onClick={refreshListings}
              className="rounded-md border border-slate-300 px-4 py-2 text-sm hover:bg-slate-50"
            >
              Filtriraj
            </button>
          </div>
        </div>

        {listings.length === 0 ? (
          <p className="text-sm text-slate-400">
            Nema pronađenih natječaja. Postavi kriterije i klikni &quot;Pokreni pretragu&quot;.
          </p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {listings.map((l) => (
              <li key={l.id} className="flex items-center justify-between gap-4 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    <span className="mr-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs uppercase text-slate-500">
                      {l.source}
                    </span>
                    {l.title}
                  </p>
                  <p className="truncate text-xs text-slate-500">
                    {l.authority || "Naručitelj nepoznat"} · CPV {l.cpv || "—"} ·{" "}
                    {l.deadline ? `rok ${new Date(l.deadline).toLocaleDateString("hr-HR")}` : "rok nepoznat"} ·{" "}
                    {l.estimatedValue != null ? `${l.estimatedValue.toLocaleString("hr-HR")} ${l.currency}` : ""}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {l.url && (
                    <a
                      href={l.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-sm text-brand-600 hover:underline"
                    >
                      Otvori
                    </a>
                  )}
                  {l.projectId ? (
                    <button
                      onClick={() => router.push(`/projects/${l.projectId}`)}
                      className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50"
                    >
                      Otvori projekt
                    </button>
                  ) : (
                    <button
                      onClick={() => createProject(l.id)}
                      disabled={creatingProjectFor === l.id}
                      className="rounded-md bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
                    >
                      {creatingProjectFor === l.id ? "Stvaram…" : "Stvori projekt"}
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function DiagnosticCard({ title, data }: { title: string; data: DiagnosticSide }) {
  return (
    <div className={`rounded-md border p-3 text-sm ${data.ok ? "border-green-200 bg-green-50" : "border-amber-200 bg-amber-50"}`}>
      <p className="font-medium">
        {title}: {data.ok ? "OK" : "Problem"}
      </p>
      <p className="mt-1 text-slate-600">{data.message}</p>
      {data.debug && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs text-slate-500">Sirovi odgovor (debug)</summary>
          <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap text-xs text-slate-500">
            {JSON.stringify(data.debug, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}
