export default function TenderSearchRoadmapPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Pretraga natječaja</h1>
      <p className="text-slate-600">
        Ova faza projekta automatski prati nove natječaje na <strong>EOJN RH</strong> (Elektronički oglasnik
        javne nabave) i <strong>TED</strong> (Tenders Electronic Daily, EU) portalima, filtrira ih prema tvojim
        kriterijima (djelatnost/CPV kod, procijenjena vrijednost, lokacija naručitelja) i automatski otvara novi
        projekt s učitanom dokumentacijom kad se pronađe relevantan natječaj.
      </p>

      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <h2 className="mb-3 text-lg font-medium">Planirano</h2>
        <ul className="list-inside list-disc space-y-2 text-sm text-slate-700">
          <li>Redovita dohvaćanja novih objava s EOJN RH i TED (API/RSS gdje je dostupno)</li>
          <li>Filtriranje po CPV kodovima, procijenjenoj vrijednosti i lokaciji naručitelja</li>
          <li>Spremanje profila tvrtke (djelatnosti, reference) radi automatskog predlaganja relevantnih natječaja</li>
          <li>Obavijesti (e-mail) o novim natječajima koji odgovaraju profilu</li>
          <li>Jednim klikom stvaranje projekta i automatski uvoz natječajne dokumentacije za analizu</li>
        </ul>
      </div>

      <div className="rounded-lg border border-dashed border-slate-300 bg-white p-6 text-sm text-slate-500">
        Za sada natječaje ručno preuzimaš s EOJN RH / TED portala i njihovu dokumentaciju učitavaš u sekciji
        &quot;Projekti&quot; kako bi dobio/la analizu i checklistu.
      </div>
    </div>
  );
}
