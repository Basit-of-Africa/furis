import Link from "next/link";

import { decideAttribution, decideAuthorship } from "@/app/actions";
import { AttributionBadge, ConfidenceBadge, MatchStatusBadge } from "@/components/badges";
import { AttributionEvidence, MatchEvidence } from "@/components/evidence";
import { ActionForm, SubmitButton } from "@/components/forms";
import { PublicationMeta } from "@/components/publication-meta";
import { ATTRIBUTION_LABEL, researcherName } from "@/lib/format";
import type { AttributionStatus, QueueItem } from "@/lib/types";

const DECIDABLE: AttributionStatus[] = [
  "confirmed_fu_output",
  "researcher_publication_not_fu",
  "not_attributable",
  "under_review",
];

export function AuthorshipActions({ item }: { item: QueueItem }) {
  const hidden = { publication_id: item.publication.id, researcher_id: item.match.researcher_id };
  return (
    <ActionForm action={decideAuthorship} hidden={hidden}>
      <label>
        Comment (optional)
        <input type="text" name="comments" placeholder="e.g. confirmed with the researcher" />
      </label>
      <div className="form-actions">
        <SubmitButton name="decision" value="confirmed">Confirm authorship</SubmitButton>
        <SubmitButton name="decision" value="rejected" variant="danger">Not this researcher</SubmitButton>
      </div>
    </ActionForm>
  );
}

export function AttributionActions({ item }: { item: QueueItem }) {
  const hidden = { publication_id: item.publication.id, researcher_id: item.match.researcher_id };
  const suggested = item.attribution?.suggested_status;
  const initial = suggested === "potential_fu_output" ? "confirmed_fu_output" : suggested === "not_attributable" ? "not_attributable" : "";
  return (
    <ActionForm action={decideAttribution} hidden={hidden}>
      <div className="form-grid">
        <label>
          Decision
          <select name="status" defaultValue={initial} required>
            <option value="" disabled>Choose…</option>
            {DECIDABLE.map((s) => <option key={s} value={s}>{ATTRIBUTION_LABEL[s]}</option>)}
          </select>
        </label>
        <label>
          Evidence (required to confirm FU output)
          <input type="text" name="evidence" placeholder="e.g. FU affiliation in Crossref; within employment" />
        </label>
      </div>
      <div className="form-actions">
        <SubmitButton>Record attribution</SubmitButton>
      </div>
    </ActionForm>
  );
}

export function ReviewItem({
  item,
  mode,
  showResearcher,
}: {
  item: QueueItem;
  mode: "authorship" | "attribution" | "readonly";
  showResearcher: boolean;
}) {
  const { match: m, publication: p, attribution: a, researcher: r } = item;
  return (
    <article className="item">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="item-title"><Link href={`/publications/${p.id}`}>{p.title}</Link></div>
          <PublicationMeta p={p} />
          {showResearcher && r && (
            <div className="item-meta">
              Candidate researcher: <Link href={`/researchers/${r.id}`}>{researcherName(r)}</Link>
              {r.staff_number && <span className="muted"> · {r.staff_number}</span>}
            </div>
          )}
        </div>
        <div className="row" style={{ justifyContent: "flex-end" }}>
          {m.match_status === "candidate" ? <ConfidenceBadge c={m.confidence} score={m.confidence_score} /> : <MatchStatusBadge s={m.match_status} />}
          <AttributionBadge a={a} />
        </div>
      </div>
      <div className="item-cols">
        <MatchEvidence m={m} />
        <AttributionEvidence a={a} />
      </div>
      {mode !== "readonly" && (
        <div style={{ marginTop: 14, borderTop: "1px solid var(--border)", paddingTop: 12 }}>
          {mode === "authorship" ? <AuthorshipActions item={item} /> : <AttributionActions item={item} />}
        </div>
      )}
    </article>
  );
}
