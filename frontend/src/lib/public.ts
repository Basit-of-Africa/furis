import "server-only";

import { API_BASE } from "./session";

/** Reads the public, read-only API (no session). Returns null when the public view is switched off.
 *  Failures are logged with their cause (visible in the hosting provider's logs), then thrown
 *  so the page's error screen can show a friendly message. */
export async function publicGet<T>(path: string): Promise<T | null> {
  const url = `${API_BASE}/public${path}`;
  let res: Response;
  try {
    res = await fetch(url, { next: { revalidate: 120 } });
  } catch (e) {
    console.error(`[FURIS] Cannot reach the API at ${API_BASE} (check FURIS_API_URL): ${(e as Error).message}`);
    throw new Error("The research data service is not reachable.");
  }
  const type = res.headers.get("content-type") ?? "";
  if (res.status === 404 && type.includes("application/json")) return null; // public view switched off
  if (!res.ok || !type.includes("application/json")) {
    const hint =
      res.status === 401 || res.status === 403
        ? "the API refused the request; if it is on Vercel, Deployment Protection may be on"
        : res.status === 404
          ? "FURIS_API_URL may point to the wrong site (expected the FURIS API)"
          : res.status >= 500
            ? "the API had an error; check its logs (database connection, migrations)"
            : !type.includes("application/json")
              ? "the response was not JSON; FURIS_API_URL may point to the wrong site"
              : "unexpected response";
    console.error(`[FURIS] ${url} returned ${res.status}: ${hint}`);
    throw new Error("The research data could not be loaded.");
  }
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
