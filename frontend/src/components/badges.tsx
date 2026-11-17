import {
  ATTRIBUTION_LABEL,
  CONFIDENCE_LABEL,
  MATCH_STATUS_LABEL,
  RUN_STATUS_LABEL,
} from "@/lib/format";
import type { Attribution, AttributionStatus, Confidence, MatchStatus } from "@/lib/types";

const CONF_TONE: Record<Confidence, string> = { high: "badge-good", medium: "badge-warn", low: "", rejected: "badge-bad" };
const MATCH_TONE: Record<MatchStatus, string> = { candidate: "badge-info", confirmed: "badge-good", rejected: "badge-bad" };
const ATTR_TONE: Record<AttributionStatus, string> = {
  confirmed_fu_output: "badge-good",
  potential_fu_output: "badge-info",
  under_review: "badge-warn",
  researcher_publication_not_fu: "",
  not_attributable: "",
};

export const ConfidenceBadge = ({ c, score }: { c: Confidence; score?: number }) => (
  <span className={`badge ${CONF_TONE[c]}`} title={score !== undefined ? `Score ${score.toFixed(2)}` : undefined}>
    {CONFIDENCE_LABEL[c]}
  </span>
);

export const MatchStatusBadge = ({ s }: { s: MatchStatus }) => (
  <span className={`badge ${MATCH_TONE[s]}`}>{MATCH_STATUS_LABEL[s]}</span>
);

/** Shows the reviewed status when there is one, otherwise the engine's suggestion, labelled as such. */
export function AttributionBadge({ a }: { a: Attribution | null }) {
  if (!a) return <span className="badge">No attribution assessment</span>;
  if (a.final_status) return <span className={`badge ${ATTR_TONE[a.final_status]}`}>{ATTRIBUTION_LABEL[a.final_status]}</span>;
  return (
    <span className={`badge ${ATTR_TONE[a.suggested_status]}`} title="System suggestion; not yet reviewed">
      Suggested: {ATTRIBUTION_LABEL[a.suggested_status]}
    </span>
  );
}

export function RunStatusBadge({ s }: { s: string }) {
  const tone = s === "completed" ? "badge-good" : s === "failed" ? "badge-bad" : s === "truncated" ? "badge-warn" : "badge-info";
  return <span className={`badge ${tone}`}>{RUN_STATUS_LABEL[s] ?? s}</span>;
}
