// Mirrors backend/furis/schemas.py. Keep in sync when the API changes.

export type Role = "super_admin" | "research_office" | "faculty_admin" | "researcher";
export type Confidence = "high" | "medium" | "low" | "rejected";
export type MatchStatus = "candidate" | "confirmed" | "rejected";
export type AttributionStatus =
  | "confirmed_fu_output"
  | "researcher_publication_not_fu"
  | "under_review"
  | "potential_fu_output"
  | "not_attributable";

export interface Me {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  faculty_id: string | null;
  researcher_id: string | null;
}

export interface Faculty { id: string; name: string; code: string | null }
export interface Department { id: string; faculty_id: string; name: string; code: string | null }

export interface ResearcherRef {
  id: string;
  first_name: string;
  middle_name: string | null;
  last_name: string;
  staff_number: string | null;
}

export interface Researcher extends ResearcherRef {
  preferred_name: string | null;
  email: string | null;
  faculty_id: string | null;
  department_id: string | null;
  employment_status: "active" | "former" | "on_leave";
}

export interface Identifier {
  id: string;
  identifier_type: string;
  identifier_value: string;
  verified: boolean;
  verified_at: string | null;
}

export interface Variant {
  id: string;
  variant_name: string;
  variant_type: "system_generated" | "researcher_confirmed" | "discovered";
  confirmation_status: "pending" | "confirmed" | "rejected";
  source: string | null;
}

export interface Employment {
  id: string;
  institution_name: string;
  is_fountain_university: boolean;
  start_date: string | null;
  end_date: string | null;
  employment_type: string | null;
  verification_status: string;
  evidence_reference: string | null;
}

export interface ResearcherDetail extends Researcher {
  identifiers: Identifier[];
  name_variants: Variant[];
  employment: Employment[];
}

export interface Publication {
  id: string;
  title: string;
  doi: string | null;
  publication_year: number | null;
  publication_date: string | null;
  document_type: string | null;
  journal_name: string | null;
  publisher: string | null;
  landing_page_url: string | null;
  is_open_access: boolean | null;
}

export interface MatchEvidenceSource {
  source?: string;
  source_record_id?: string;
  raw_name?: string;
  name_kind?: string;
  name_score?: number;
  identifier?: string;
  orcid?: string;
  warning?: string;
  signals?: string[];
}

export interface Match {
  id: string;
  publication_id: string;
  researcher_id: string;
  author_position: number | null;
  matching_method: string;
  confidence: Confidence;
  confidence_score: number;
  evidence_summary: { sources?: MatchEvidenceSource[] };
  match_status: MatchStatus;
  reviewed_at: string | null;
}

export interface Attribution {
  id: string;
  publication_id: string;
  researcher_id: string;
  suggested_status: AttributionStatus;
  final_status: AttributionStatus | null;
  evidence: {
    reasons?: string[];
    fu_affiliation_in_metadata?: boolean;
    other_affiliations?: string[];
    employment_positions?: string[];
    publication_date?: string | null;
    publication_year?: number | null;
  };
  policy_version: string;
  decided_at: string | null;
}

export interface QueueItem {
  match: Match;
  publication: Publication;
  attribution: Attribution | null;
  researcher: ResearcherRef | null;
}

export interface Source {
  source_name: string;
  source_record_id: string;
  source_url: string | null;
  citation_count: number | null;
  retrieved_at: string;
}

export interface Author {
  author_position: number;
  raw_author_name: string;
  orcid: string | null;
  researcher_id: string | null;
  identity_status: MatchStatus | null;
}

export interface Affiliation {
  researcher_id: string | null;
  author_position: number | null;
  raw_affiliation: string;
  normalised_institution: string | null;
  is_fountain_university: boolean;
  source_name: string;
}

export interface PublicationDetail extends Publication {
  sources: Source[];
  authors: Author[];
  matches: Match[];
  attributions: Attribution[];
  affiliations: Affiliation[];
  researchers: ResearcherRef[];
}

export interface HistoryEntry {
  type: "authorship" | "attribution";
  decision: string;
  researcher_id: string;
  reviewer_id: string;
  reviewer_name: string | null;
  evidence: string | null;
  comments: string | null;
  verified_at: string;
}

export interface SearchRun {
  id: string;
  batch_id: string;
  source_name: string;
  search_query: string;
  query_type: string;
  started_at: string;
  completed_at: string | null;
  records_found: number;
  records_processed: number;
  unique_records_found: number;
  candidates_matched: number;
  error_message: string | null;
  run_status: "running" | "completed" | "truncated" | "failed";
}

export interface Duplicate {
  id: string;
  publication_id: string;
  other_publication_id: string;
  similarity: number;
  reason: string;
  status: "pending" | "merged" | "distinct";
  publication: Publication | null;
  other_publication: Publication | null;
}

export interface Summary {
  researchers: number;
  publications_discovered: number;
  confirmed_researcher_publications: number;
  awaiting_authorship_review: number;
  confirmed_fu_output: number;
  awaiting_attribution_review: number;
  fu_output_by_year: { year: number | null; count: number }[];
  fu_output_by_faculty: { faculty_id: string | null; count: number }[];
  pct_researchers_verified_orcid: number;
  pct_researchers_with_confirmed_publications: number;
  search_runs_by_status: Record<string, number>;
}

export type ActionResult = { ok: boolean; message?: string } | null;
