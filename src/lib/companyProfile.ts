import { prisma } from "@/lib/db";

// Aplikacija je jednokorisnička (jedna tvrtka), pa uvijek radimo s jednim (prvim) profilom.
export async function getOrCreateCompanyProfile() {
  const existing = await prisma.companyProfile.findFirst();
  if (existing) return existing;

  return prisma.companyProfile.create({ data: { name: "Moja tvrtka" } });
}
