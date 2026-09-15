import { notFound } from "next/navigation";
import { prisma } from "@/lib/db";
import ProjectWorkspace from "@/components/ProjectWorkspace";

export default async function ProjectPage({ params }: { params: { id: string } }) {
  const project = await prisma.project.findUnique({
    where: { id: params.id },
    include: {
      documents: { orderBy: { createdAt: "asc" } },
      checklistItems: { orderBy: { createdAt: "asc" } },
      requirements: { orderBy: { createdAt: "asc" } },
      analyses: { orderBy: { createdAt: "desc" }, take: 1 },
      generatedOffers: { orderBy: { createdAt: "desc" } },
    },
  });

  if (!project) {
    notFound();
  }

  return <ProjectWorkspace project={project} />;
}

export const dynamic = "force-dynamic";
