import { prisma } from "@/lib/db";
import type { SearchCriteria } from "@/lib/providers/types";

export async function getOrCreateSearchProfile() {
  const existing = await prisma.searchProfile.findFirst();
  if (existing) return existing;
  return prisma.searchProfile.create({ data: {} });
}

export function profileToCriteria(profile: {
  cpvCodes: string | null;
  keywords: string | null;
  minValue: number | null;
  maxValue: number | null;
  county: string | null;
}): SearchCriteria {
  return {
    cpvCodes: (profile.cpvCodes ?? "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean),
    keywords: (profile.keywords ?? "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean),
    minValue: profile.minValue ?? undefined,
    maxValue: profile.maxValue ?? undefined,
    county: profile.county ?? undefined,
  };
}
