"use client";

import { useRef, useState } from "react";

interface CompetitorDto {
  id: string;
  name: string;
  notes: string | null;
  _count: { awards: number };
}

interface AwardDto {
  id: string;
  winnerName: string;
  authority: string | null;
  cpv: string | null;
  tenderTitle: string;
  value: number | null;
  currency: string;
  awardDate: string | Date | null;
  productsText: string | null;
  competitor: { id: string; name: string } | null;
}

export default function CompetitorsWorkspace({
  initialCompetitors,
  initialAwards,
}: {
  initialCompetitors: CompetitorDto[];
  initialAwards: AwardDto[];
}) {
  const [competitors, setCompetitors] = useState(initialCompetitors);
  const [awards, setAwards] = useState(initialAwards);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const [newCompetitorName, setNewCompetitorName] = useState("");
  const csvInputRef = useRef<HTMLInputElement>(null);
  const [importing, setImporting] = useState(false);

  const [filterCompetitor, setFilterCompetitor] = useState("");
  const [filterCpv, setFilterCpv] = useState("");
  const [filterQ, setFilterQ] = useState("");
  const [loadingAwards, setLoadingAwards] = useState(false);

  const [manualForm, setManualForm] = useState({
    winnerName: "",
    authority: "",
    cpv: "",
    tenderTitle: "",
    value: "",
    currency: "EUR",
    awardDate: "",
    productsText: "",
    sourceUrl: "",
  });
  const [savingManual, setSavingManual] = useState(false);

  const [analyzing, setAnalyzing] = useState(false);
  const [analysis, setAnalysis] = useState<string | null>(null);

  async function refreshCompetitors() {
    const res = await fetch("/api/competitors");
    const data = await res.json();
    setCompetitors(data.competitors);
  }

  async function refreshAwards() {
    setLoadingAwards(true);
    const params = new URLSearchParams();
    if (filterCompetitor) params.set("competitorId", filterCompetitor);
    if (filterCpv) params.set("cpv", filterCpv);
    if (filterQ) params.set("q", filterQ);
    const res = await fetch(`/api/competitor-awards?${params.toString()}`);
    const data = await res.json();
    setAwards(data.awards);
    setLoadingAwards(false);
  }

  async function addCompetitor(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const res = await fetch("/api/competitors", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: newCompetitorName }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      setError(data.error || "Dodavanje konkurenta nije uspjelo.");
      return;
    }
    setNewCompetitorName("");
    refreshCompetitors();
  }

  async function deleteCompetitor(id: string) {
    await fetch(`/api/competitors/${id}`, { method: "DELETE" });
    refreshCompetitors();
    refreshAwards();
  }

  async function handleImportCsv() {
    const file = csvInputRef.current?.files?.[0];
    if (!file) return;
    setImporting(true);
    setError(null);
    setInfo(null);

    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch("/api/competitor-awards/import", { method: "POST", body: formData });
    setImporting(false);

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      setError(data.error || "Uvoz nije uspio.");
      return;
    }
    const data = await res.json();
    setInfo(
      `Uvezeno ${data.imported} zapisa.` +
        (data.errors?.length ? ` Preskočeno ${data.errors.length} redaka s greškom.` : ""),
    );
    if (csvInputRef.current) csvInputRef.current.value = "";
    refreshAwards();
  }

  async function addManualAward(e: React.FormEvent) {
    e.preventDefault();
    setSavingManual(true);
    setError(null);

    const res = await fetch("/api/competitor-awards", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...manualForm,
        value: manualForm.value ? Number(manualForm.value) : null,
      }),
    });

    setSavingManual(false);

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      setError(data.error || "Spremanje zapisa nije uspjelo.");
      return;
    }

    setManualForm({
      winnerName: "",
      authority: "",
      cpv: "",
      tenderTitle: "",
      value: "",
      currency: "EUR",
      awardDate: "",
      productsText: "",
      sourceUrl: "",
    });
    refreshAwards();
  }

  async function handleAnalyze() {
    setAnalyzing(true);
    setError(null);
    setAnalysis(null);

    const res = await fetch("/api/competitor-awards/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        competitorId: filterCompetitor || undefined,
        cpv: filterCpv || undefined,
        q: filterQ || undefined,
      }),
    });

    setAnalyzing(false);

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      setError(data.error || "Analiza nije uspjela.");
      return;
    }

    const data = await res.json();
    setAnalysis(data.analysis);
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">Konkurencija</h1>
        <p className="text-sm text-slate-500">
          Baza javno objavljenih dodjela ugovora (iz Obavijesti o dodjeli na EOJN RH / TED) po tvojim
          konkurentima i djelatnosti (CPV). Automatsko preuzimanje s portala je planirano — za sada podatke
          dodaješ ručno ili uvoziš CSV izvozom s portala.
        </p>
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}
      {info && (
        <div className="rounded-md border border-brand-100 bg-brand-50 px-4 py-3 text-sm text-brand-700">{info}</div>
      )}

      <section className="rounded-lg border border-slate-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-medium">Praćeni konkurenti</h2>
        <form onSubmit={addCompetitor} className="mb-4 flex gap-3">
          <input
            value={newCompetitorName}
            onChange={(e) => setNewCompetitorName(e.target.value)}
            placeholder="Naziv tvrtke konkurenta"
            required
            className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <button className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700">
            Dodaj
          </button>
        </form>
        {competitors.length === 0 ? (
          <p className="text-sm text-slate-400">Još nema dodanih konkurenata.</p>
        ) : (
          <ul className="flex flex-wrap gap-2">
            {competitors.map((c) => (
              <li
                key={c.id}
                className="flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-700"
              >
                {c.name} <span className="text-slate-400">({c._count.awards})</span>
                <button onClick={() => deleteCompetitor(c.id)} className="text-red-500 hover:underline">
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-medium">Uvoz podataka o dodjelama (CSV)</h2>
        <p className="mb-3 text-sm text-slate-500">
          Stupci: <code>winnerName, authority, cpv, tenderTitle, value, currency, awardDate, productsText, sourceUrl</code>{" "}
          (prvi red je header; <code>winnerName</code> i <code>tenderTitle</code> su obavezni).
        </p>
        <div className="flex items-center gap-3">
          <input ref={csvInputRef} type="file" accept=".csv,text/csv" className="text-sm" />
          <button
            onClick={handleImportCsv}
            disabled={importing}
            className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {importing ? "Uvozim…" : "Uvezi CSV"}
          </button>
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-medium">Ručni unos dodjele ugovora</h2>
        <form onSubmit={addManualAward} className="grid gap-3 sm:grid-cols-2">
          <input
            required
            placeholder="Pobjednik (naziv tvrtke) *"
            value={manualForm.winnerName}
            onChange={(e) => setManualForm((f) => ({ ...f, winnerName: e.target.value }))}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <input
            required
            placeholder="Naziv natječaja *"
            value={manualForm.tenderTitle}
            onChange={(e) => setManualForm((f) => ({ ...f, tenderTitle: e.target.value }))}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <input
            placeholder="Naručitelj"
            value={manualForm.authority}
            onChange={(e) => setManualForm((f) => ({ ...f, authority: e.target.value }))}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <input
            placeholder="CPV kod"
            value={manualForm.cpv}
            onChange={(e) => setManualForm((f) => ({ ...f, cpv: e.target.value }))}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <input
            type="number"
            step="0.01"
            placeholder="Vrijednost"
            value={manualForm.value}
            onChange={(e) => setManualForm((f) => ({ ...f, value: e.target.value }))}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <input
            type="date"
            value={manualForm.awardDate}
            onChange={(e) => setManualForm((f) => ({ ...f, awardDate: e.target.value }))}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <input
            placeholder="Izvor (URL objave)"
            value={manualForm.sourceUrl}
            onChange={(e) => setManualForm((f) => ({ ...f, sourceUrl: e.target.value }))}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm sm:col-span-2"
          />
          <textarea
            placeholder="Opis proizvoda / usluga / stavki"
            value={manualForm.productsText}
            onChange={(e) => setManualForm((f) => ({ ...f, productsText: e.target.value }))}
            rows={2}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm sm:col-span-2"
          />
          <button
            disabled={savingManual}
            className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50 sm:col-span-2"
          >
            {savingManual ? "Spremam…" : "Dodaj zapis"}
          </button>
        </form>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-medium">Podaci o dodjelama</h2>
          <button
            onClick={handleAnalyze}
            disabled={analyzing}
            className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {analyzing ? "Analiziram…" : "AI analiza cijena i proizvoda"}
          </button>
        </div>

        <div className="mb-4 flex flex-wrap gap-3">
          <select
            value={filterCompetitor}
            onChange={(e) => setFilterCompetitor(e.target.value)}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="">Svi konkurenti</option>
            {competitors.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <input
            placeholder="Filter po CPV"
            value={filterCpv}
            onChange={(e) => setFilterCpv(e.target.value)}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <input
            placeholder="Pretraga (naziv, naručitelj, proizvod…)"
            value={filterQ}
            onChange={(e) => setFilterQ(e.target.value)}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <button
            onClick={refreshAwards}
            disabled={loadingAwards}
            className="rounded-md border border-slate-300 px-4 py-2 text-sm hover:bg-slate-50"
          >
            {loadingAwards ? "Filtriram…" : "Filtriraj"}
          </button>
        </div>

        {analysis && (
          <div className="mb-4 whitespace-pre-line rounded-md bg-slate-50 p-4 text-sm text-slate-700">
            {analysis}
          </div>
        )}

        {awards.length === 0 ? (
          <p className="text-sm text-slate-400">Nema podataka koji odgovaraju filteru.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-xs uppercase text-slate-500">
                  <th className="py-2 pr-3">Datum</th>
                  <th className="py-2 pr-3">Pobjednik</th>
                  <th className="py-2 pr-3">Naručitelj</th>
                  <th className="py-2 pr-3">CPV</th>
                  <th className="py-2 pr-3">Natječaj</th>
                  <th className="py-2 pr-3">Vrijednost</th>
                </tr>
              </thead>
              <tbody>
                {awards.map((a) => (
                  <tr key={a.id} className="border-b border-slate-100">
                    <td className="py-2 pr-3 whitespace-nowrap">
                      {a.awardDate ? new Date(a.awardDate).toLocaleDateString("hr-HR") : "—"}
                    </td>
                    <td className="py-2 pr-3">{a.winnerName}</td>
                    <td className="py-2 pr-3">{a.authority || "—"}</td>
                    <td className="py-2 pr-3">{a.cpv || "—"}</td>
                    <td className="py-2 pr-3">{a.tenderTitle}</td>
                    <td className="py-2 pr-3 whitespace-nowrap">
                      {a.value != null ? `${a.value.toLocaleString("hr-HR")} ${a.currency}` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
