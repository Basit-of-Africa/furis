import "server-only";

import { API_BASE } from "./session";

/** Reads the public, read-only API (no session). Returns null when the public view is switched off. */
export async function publicGet<T>(path: string): Promise<T | null> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/public${path}`, { next: { revalidate: 120 } });
  } catch {
    throw new Error("The research data service is not reachable. Please try again shortly.");
  }
  if (res.status === 404) return null;
  if (!res.ok) throw new Error("The research data could not be loaded.");
  return (await res.json()) as T;
}

export interface PublicPerson {
  id: string;
  name: string;
  faculty: string | null;
  department: string | null;
}

export interface PublicPublication {
  id: string;
  title: string;
  doi: string | null;
  publication_year: number | null;
  publication_date: string | null;
  journal_name: string | null;
  document_type: string | null;
  landing_page_url: string | null;
  is_open_access: boolean | null;
  fu_output: boolean;
  researchers: PublicPerson[];
}

export interface PublicResearcher extends PublicPerson {
  orcid: string | null;
  publication_count: number;
  fu_output_count: number;
}

export interface PublicResearcherDetail extends PublicResearcher {
  publications: PublicPublication[];
}

export interface PublicSummary {
  fu_output: number;
  researcher_publications: number;
  researchers: number;
  fu_output_by_year: { year: number | null; count: number }[];
  faculties: { id: string; name: string; fu_output: number }[];
}
