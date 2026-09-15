"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

interface TemplateDto {
  id: string;
  title: string;
  originalName: string;
}

interface ProfileDto {
  id: string;
  name: string;
  oib: string | null;
  address: string | null;
  contactEmail: string | null;
  contactPhone: string | null;
  iban: string | null;
  description: string | null;
  templates: TemplateDto[];
}

export default function CompanyProfileForm({ profile }: { profile: ProfileDto }) {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const titleInputRef = useRef<HTMLInputElement>(null);

  const [form, setForm] = useState({
    name: profile.name,
    oib: profile.oib ?? "",
    address: profile.address ?? "",
    contactEmail: profile.contactEmail ?? "",
    contactPhone: profile.contactPhone ?? "",
    iban: profile.iban ?? "",
    description: profile.description ?? "",
  });
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function update<K extends keyof typeof form>(key: K, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
    setSaved(false);
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);

    const res = await fetch("/api/company", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form),
    });

    setSaving(false);

    if (!res.ok) {
      setError("Spremanje nije uspjelo.");
      return;
    }

    setSaved(true);
    router.refresh();
  }

  async function handleUploadTemplate() {
    const file = fileInputRef.current?.files?.[0];
    if (!file) return;

    setUploading(true);
    setError(null);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("title", titleInputRef.current?.value || "");

    const res = await fetch("/api/company/templates", { method: "POST", body: formData });
    setUploading(false);

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      setError(data.error || "Upload predloška nije uspio.");
      return;
    }

    if (fileInputRef.current) fileInputRef.current.value = "";
    if (titleInputRef.current) titleInputRef.current.value = "";
    router.refresh();
  }

  async function handleDeleteTemplate(id: string) {
    await fetch(`/api/company/templates/${id}`, { method: "DELETE" });
    router.refresh();
  }

  return (
    <div className="space-y-6">
      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      <form onSubmit={handleSave} className="space-y-4 rounded-lg border border-slate-200 bg-white p-6">
        <h2 className="text-lg font-medium">Podaci tvrtke</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Naziv tvrtke" value={form.name} onChange={(v) => update("name", v)} required />
          <Field label="OIB" value={form.oib} onChange={(v) => update("oib", v)} />
          <Field label="Adresa" value={form.address} onChange={(v) => update("address", v)} />
          <Field label="IBAN" value={form.iban} onChange={(v) => update("iban", v)} />
          <Field label="Kontakt e-mail" value={form.contactEmail} onChange={(v) => update("contactEmail", v)} />
          <Field label="Kontakt telefon" value={form.contactPhone} onChange={(v) => update("contactPhone", v)} />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">
            Opis djelatnosti / reference / iskustvo
          </label>
          <textarea
            value={form.description}
            onChange={(e) => update("description", e.target.value)}
            rows={4}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
            placeholder="Ovaj tekst AI koristi za sastavljanje dijela ponude o sposobnosti i referencama."
          />
        </div>
        <button
          type="submit"
          disabled={saving}
          className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {saving ? "Spremam…" : saved ? "Spremljeno ✓" : "Spremi podatke"}
        </button>
      </form>

      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-medium">Vlastiti predlošci (obrasci, troškovnik…)</h2>
        <div className="flex flex-wrap items-center gap-3">
          <input
            ref={titleInputRef}
            type="text"
            placeholder="Naziv predloška (opcionalno)"
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <input ref={fileInputRef} type="file" accept=".pdf,.docx,.txt" className="text-sm" />
          <button
            onClick={handleUploadTemplate}
            disabled={uploading}
            className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {uploading ? "Učitavam…" : "Dodaj predložak"}
          </button>
        </div>

        {profile.templates.length === 0 ? (
          <p className="mt-4 text-sm text-slate-400">Nema dodanih predložaka.</p>
        ) : (
          <ul className="mt-4 divide-y divide-slate-100">
            {profile.templates.map((t) => (
              <li key={t.id} className="flex items-center justify-between py-2 text-sm">
                <span>
                  📎 <strong>{t.title}</strong>{" "}
                  <span className="text-slate-400">({t.originalName})</span>
                </span>
                <button
                  onClick={() => handleDeleteTemplate(t.id)}
                  className="text-xs text-red-600 hover:underline"
                >
                  Ukloni
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  required,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  required?: boolean;
}) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-slate-700">{label}</label>
      <input
        required={required}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
      />
    </div>
  );
}
