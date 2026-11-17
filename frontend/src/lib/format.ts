import type { AttributionStatus, Confidence, MatchStatus, ResearcherRef, Role } from "./types";

export const isAdmin = (role: Role) => role === "super_admin" || role === "research_office";

export function researcherName(r: Pick<ResearcherRef, "first_name" | "middle_name" | "last_name"> | null) {
  if (!r) return "Unknown researcher";
  return [r.first_name, r.middle_name, r.last_name].filter(Boolean).join(" ");
}

/** External metadata is untrusted: only allow http(s) links (blocks javascript: etc.). */
export function safeUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const u = new URL(url);
    return u.protocol === "https:" || u.protocol === "http:" ? u.toString() : null;
  } catch {
    return null;
  }
}

export const doiUrl = (doi: string | null) => (doi ? `https://doi.org/${encodeURI(doi)}` : null);

export const ROLE_LABEL: Record<Role, string> = {
  super_admin: "Super Administrator",
  research_office: "Research Office",
  faculty_admin: "Faculty Administrator",
  researcher: "Researcher",
};

export const CONFIDENCE_LABEL: Record<Confidence, string> = {
  high: "High confidence",
  medium: "Medium confidence",
  low: "Low confidence",
  rejected: "Rejected by evidence",
};

export const MATCH_STATUS_LABEL: Record<MatchStatus, string> = {
  candidate: "Awaiting authorship review",
  confirmed: "Authorship confirmed",
  rejected: "Not this researcher",
};

export const ATTRIBUTION_LABEL: Record<AttributionStatus, string> = {
  confirmed_fu_output: "Confirmed FU output",
  researcher_publication_not_fu: "Researcher's publication, not FU output",
  under_review: "Attribution under review",
  potential_fu_output: "Potential FU output",
  not_attributable: "Not attributable to FU",
};

export const RUN_STATUS_LABEL: Record<string, string> = {
  running: "Running",
  completed: "Completed",
  truncated: "Truncated at record cap",
  failed: "Failed",
};

export function methodLabel(method: string): string {
  const map: Record<string, string> = {
    orcid: "Verified ORCID on byline",
    orcid_record: "Listed on researcher's ORCID record",
    openalex_author_id: "Confirmed OpenAlex author ID",
    orcid_conflict: "Byline carries a different ORCID",
    "name:exact": "Full name match",
    "name:full_partial": "Partial full-name match",
    "name:initials": "Initials and surname",
    "name:surname_only": "Surname only",
  };
  return map[method] ?? method;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}
