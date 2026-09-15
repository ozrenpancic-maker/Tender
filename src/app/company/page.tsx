import { prisma } from "@/lib/db";
import { getOrCreateCompanyProfile } from "@/lib/companyProfile";
import CompanyProfileForm from "@/components/CompanyProfileForm";

export default async function CompanyPage() {
  const profile = await getOrCreateCompanyProfile();
  const full = await prisma.companyProfile.findUnique({
    where: { id: profile.id },
    include: { templates: { orderBy: { createdAt: "asc" } } },
  });

  if (!full) return null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Profil tvrtke</h1>
        <p className="text-sm text-slate-500">
          Ovi podaci i predlošci koriste se za automatsko sastavljanje nacrta ponude u svakom projektu.
        </p>
      </div>
      <CompanyProfileForm profile={full} />
    </div>
  );
}

export const dynamic = "force-dynamic";
