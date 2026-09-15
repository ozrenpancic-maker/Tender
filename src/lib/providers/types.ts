export interface SearchCriteria {
  cpvCodes: string[];
  keywords: string[];
  minValue?: number;
  maxValue?: number;
  county?: string;
}

export interface NormalizedListing {
  source: "ted" | "eojn";
  externalId: string;
  title: string;
  authority?: string;
  cpv?: string;
  publishedDate?: Date;
  deadline?: Date;
  estimatedValue?: number;
  currency?: string;
  noticeType?: string;
  url?: string;
  rawExcerpt?: string;
}

export interface ProviderResult {
  ok: boolean;
  listings: NormalizedListing[];
  message: string; // ljudski čitljiva dijagnostika (status, broj rezultata, upozorenja)
}
