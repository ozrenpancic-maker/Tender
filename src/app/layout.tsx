import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Tender OP – asistent za javnu nabavu",
  description: "Učitaj natječajnu dokumentaciju i dobij checklistu i ključne zahtjeve za ponudu.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="hr">
      <body>
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4">
            <Link href="/" className="text-lg font-semibold text-brand-700">
              Tender<span className="text-slate-900">OP</span>
            </Link>
            <nav className="flex gap-4 text-sm text-slate-600">
              <Link href="/" className="hover:text-brand-700">
                Projekti
              </Link>
              <Link href="/pretraga-natjecaja" className="hover:text-brand-700">
                Pretraga natječaja
              </Link>
              <Link href="/konkurencija" className="hover:text-brand-700">
                Konkurencija
              </Link>
              <Link href="/company" className="hover:text-brand-700">
                Profil tvrtke
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-5xl px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
