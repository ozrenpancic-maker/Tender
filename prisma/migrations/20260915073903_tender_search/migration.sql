-- CreateTable
CREATE TABLE "SearchProfile" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "cpvCodes" TEXT,
    "keywords" TEXT,
    "minValue" REAL,
    "maxValue" REAL,
    "county" TEXT,
    "sourceTed" BOOLEAN NOT NULL DEFAULT true,
    "sourceEojn" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL
);

-- CreateTable
CREATE TABLE "TenderListing" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "source" TEXT NOT NULL,
    "externalId" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "authority" TEXT,
    "cpv" TEXT,
    "publishedDate" DATETIME,
    "deadline" DATETIME,
    "estimatedValue" REAL,
    "currency" TEXT NOT NULL DEFAULT 'EUR',
    "noticeType" TEXT,
    "url" TEXT,
    "rawExcerpt" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "projectId" TEXT,
    CONSTRAINT "TenderListing_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES "Project" ("id") ON DELETE SET NULL ON UPDATE CASCADE
);

-- CreateIndex
CREATE UNIQUE INDEX "TenderListing_projectId_key" ON "TenderListing"("projectId");

-- CreateIndex
CREATE UNIQUE INDEX "TenderListing_source_externalId_key" ON "TenderListing"("source", "externalId");
