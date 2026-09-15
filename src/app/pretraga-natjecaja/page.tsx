import { prisma } from "@/lib/db";
import { getOrCreateSearchProfile } from "@/lib/searchProfile";
import TenderSearchWorkspace from "@/components/TenderSearchWorkspace";

export default async function TenderSearchPage() {
  const [profile, listings] = await Promise.all([
    getOrCreateSearchProfile(),
    prisma.tenderListing.findMany({ orderBy: { createdAt: "desc" }, take: 200 }),
  ]);

  return <TenderSearchWorkspace initialProfile={profile} initialListings={listings} />;
}

export const dynamic = "force-dynamic";
