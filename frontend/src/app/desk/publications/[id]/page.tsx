import Link from "next/link";
import { notFound } from "next/navigation";

import { AttributionBadge, ConfidenceBadge, MatchStatusBadge } from "@/components/badges";
import { AttributionEvidence, MatchEvidence } from "@/components/evidence";
import { PublicationMeta } from "@/components/publication-meta";
import { AttributionActions, AuthorshipActions } from "@/components/review-item";
import { apiGetOptional, getMe, qs } from "@/lib/api";
import { ATTRIBUTION_LABEL, fmtDate, fmtDateTime, isAdmin, researcherName, safeUrl } from "@/lib/format";
import type { AttributionStatus, HistoryEntry, PublicationDetail, QueueItem } from "@/lib/types";

export const metadata = { title: "Publication" };

export default async function PublicationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const me = await getMe();
  const [pub, history] = await Promise.all([
    apiGetOptional<PublicationDetail>(`/publications/${encodeURIComponent(id)}`),
    apiGetOptional<HistoryEntry[]>(`/verification/history${qs({ publication_id: id })}`),
  ]);
  if (!pub) notFound();
  const admin = isAdmin(me.role);
  const names = new Map(pub.researchers.map((r) => [r.id, r]));
  const linkedPositions = new Set(pub.authors.filter((a) => a.researcher_id).map((a) => a.author_position));

  return (
    <>
      <div className="page-head">
        <div style={{ minWidth: 0 }}>
          <div className="crumbs"><Link href="/desk/publications">Publications</Link> /</div>
          <h1>{pub.title}</h1>
          <PublicationMeta p={pub} />
        </div>
      </div>

      <div className="grid-main">
        <div className="stack">
          {pub.matches.length === 0 && <div className="card empty">No researcher you can see is linked to this publication.</div>}
          {pub.matches.map((m) => {
            const r = names.get(m.researcher_id) ?? null;
            const a = pub.attributions.find((x) => x.researcher_id === m.researcher_id) ?? null;
            const item: QueueItem = { match: m, publication: pub, attribution: a, researcher: r };
            const canAuthor = m.match_status === "candidate" && (admin || me.researcher_id === m.researcher_id);
            const canAttribute = admin && m.match_status === "confirmed";
            return (
              <section className="card" key={m.id}>
                <div className="card-head">
                  <h2>{r ? <Link href={`/desk/researchers/${r.id}`}>{researcherName(r)}</Link> : "Researcher"}</h2>
                  <div className="row">
                    {m.match_status === "candidate" ? <ConfidenceBadge c={m.confidence} score={m.confidence_score} /> : <MatchStatusBadge s={m.match_status} />}
                    <AttributionBadge a={a} />
                  </div>
                </div>
                <div className="item-cols" style={{ marginTop: 0 }}>
                  <MatchEvidence m={m} />
                  <AttributionEvidence a={a} />
                </div>
                {a?.final_status && (
                  <p className="small muted" style={{ marginTop: 8 }}>
                    System suggestion: {ATTRIBUTION_LABEL[a.suggested_status]}. Reviewer decision ({fmtDate(a.decided_at)}):{" "}
                    {ATTRIBUTION_LABEL[a.final_status]}.
                  </p>
                )}
                {(canAuthor || canAttribute) && (
                  <div style={{ marginTop: 14, borderTop: "1px solid var(--border)", paddingTop: 12 }}>
                    {canAuthor && <AuthorshipActions item={item} />}
                    {canAttribute && (
                      <>
                        <div className="section-label">{a?.final_status ? "Change attribution decision" : "Attribution decision"}</div>
                        <AttributionActions item={item} />
                      </>
                    )}
                  </div>
                )}
                {admin && m.match_status === "candidate" && (
                  <p className="small muted" style={{ marginTop: 8 }}>Attribution can be decided once authorship is confirmed.</p>
                )}
              </section>
            );
          })}

          <section className="card">
            <h2>Authors</h2>
            <div className="author-list">
              {pub.authors.map((a) => (
                <span key={a.author_position} className={`author ${linkedPositions.has(a.author_position) ? "linked" : ""}`}
                      title={a.orcid ? `ORCID ${a.orcid}` : undefined}>
                  {a.raw_author_name}
                </span>
              ))}
              {pub.authors.length === 0 && <span className="muted small">This source gave no author list (for example, an ORCID record).</span>}
            </div>
            <p className="small muted" style={{ marginTop: 8 }}>Highlighted names are confirmed FURIS researchers.</p>
          </section>

          <section className="card">
            <h2>Affiliation evidence</h2>
            {pub.affiliations.length ? (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Affiliation as published</th><th>Source</th><th>FU</th></tr></thead>
                  <tbody>
                    {pub.affiliations.map((a, i) => (
                      <tr key={i}>
                        <td>{a.raw_affiliation}</td>
                        <td>{a.source_name}</td>
                        <td>{a.is_fountain_university ? <span className="badge badge-good">Fountain University</span> : <span className="muted">No</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <p className="muted small">No affiliation text was supplied by the sources for the matched author.</p>}
          </section>
        </div>

        <div className="stack">
          <section className="card">
            <h2>Record</h2>
            <dl className="kv">
              <dt>DOI</dt><dd className="mono">{pub.doi ?? "—"}</dd>
              <dt>Published</dt><dd>{pub.publication_date ? fmtDate(pub.publication_date) : pub.publication_year ?? "—"}</dd>
              <dt>Type</dt><dd>{pub.document_type ?? "—"}</dd>
              <dt>Venue</dt><dd>{pub.journal_name ?? "—"}</dd>
              <dt>Publisher</dt><dd>{pub.publisher ?? "—"}</dd>
              <dt>Open access</dt><dd>{pub.is_open_access === null ? "Unknown" : pub.is_open_access ? "Yes" : "No"}</dd>
            </dl>
          </section>

          <section className="card">
            <h2>Sources</h2>
            <p className="small muted" style={{ marginBottom: 8 }}>Citation counts are per source and are never combined.</p>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Source</th><th className="num">Citations</th><th>Retrieved</th></tr></thead>
                <tbody>
                  {pub.sources.map((s) => {
                    const url = safeUrl(s.source_url);
                    return (
                      <tr key={`${s.source_name}-${s.source_record_id}`}>
                        <td>
                          {url ? <a href={url} target="_blank" rel="noopener noreferrer nofollow">{s.source_name}</a> : s.source_name}
                          <div className="small muted mono" style={{ overflowWrap: "anywhere" }}>{s.source_record_id}</div>
                        </td>
                        <td className="num">{s.citation_count ?? "—"}</td>
                        <td className="small">{fmtDate(s.retrieved_at)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          <section className="card">
            <h2>Decision history</h2>
            {history?.length ? (
              <ol className="evidence" style={{ paddingLeft: 18 }}>
                {history.map((h, i) => (
                  <li key={i} style={{ marginBottom: 8 }}>
                    <strong>{h.type === "authorship" ? "Authorship" : "Attribution"}:</strong>{" "}
                    {h.type === "attribution" ? ATTRIBUTION_LABEL[h.decision as AttributionStatus] ?? h.decision : h.decision}
                    <div className="muted">
                      {fmtDateTime(h.verified_at)} · by {h.reviewer_name ?? "unknown reviewer"}
                      {pub.matches.length > 1 && names.get(h.researcher_id) ? ` · for ${researcherName(names.get(h.researcher_id)!)}` : ""}
                    </div>
                    {h.evidence && <div>Evidence: {h.evidence}</div>}
                    {h.comments && <div>Comment: {h.comments}</div>}
                  </li>
                ))}
              </ol>
            ) : <p className="muted small">No decisions yet.</p>}
          </section>
        </div>
      </div>
    </>
  );
}
