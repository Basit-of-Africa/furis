import Link from "next/link";
import { notFound } from "next/navigation";

import {
  addAlias,
  addEmployment,
  addIdentifier,
  reviewVariant,
  startDiscovery,
  verifyIdentifier,
} from "@/app/actions";
import { AttributionBadge, ConfidenceBadge, MatchStatusBadge, RunStatusBadge } from "@/components/badges";
import { ActionForm, SubmitButton } from "@/components/forms";
import { apiGet, apiGetOptional, getMe, qs } from "@/lib/api";
import { fmtDate, fmtDateTime, isAdmin, researcherName } from "@/lib/format";
import type { Department, Faculty, QueueItem, ResearcherDetail, SearchRun } from "@/lib/types";

export const metadata = { title: "Researcher" };

const ID_LABEL: Record<string, string> = {
  orcid: "ORCID",
  openalex: "OpenAlex author",
  scopus: "Scopus Author ID",
  wos_researcher_id: "Web of Science ResearcherID",
  google_scholar: "Google Scholar profile",
  semantic_scholar: "Semantic Scholar",
  other: "Other",
};
const VARIANT_LABEL = { system_generated: "Generated", researcher_confirmed: "Confirmed alias", discovered: "Discovered" };

export default async function ResearcherPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const me = await getMe();
  const r = await apiGetOptional<ResearcherDetail>(`/researchers/${encodeURIComponent(id)}`);
  if (!r) notFound();
  const admin = isAdmin(me.role);
  const self = me.researcher_id === r.id;
  const canEditNames = admin || self;

  const [matches, runs, faculties, departments] = await Promise.all([
    apiGet<QueueItem[]>(`/researchers/${r.id}/matches`),
    apiGet<SearchRun[]>(`/discovery/runs${qs({ researcher_id: r.id, limit: 60 })}`),
    apiGet<Faculty[]>("/faculties"),
    apiGet<Department[]>("/departments"),
  ]);
  const fac = faculties.find((f) => f.id === r.faculty_id);
  const dep = departments.find((d) => d.id === r.department_id);
  const counts = {
    candidate: matches.filter((m) => m.match.match_status === "candidate").length,
    confirmed: matches.filter((m) => m.match.match_status === "confirmed").length,
    fu: matches.filter((m) => m.attribution?.final_status === "confirmed_fu_output").length,
  };
  const pending = r.name_variants.filter((v) => v.variant_type === "discovered" && v.confirmation_status === "pending");
  const otherVariants = r.name_variants.filter((v) => !pending.includes(v));
  const latestBatch = runs[0]?.batch_id;
  const latestRuns = runs.filter((x) => x.batch_id === latestBatch);

  return (
    <>
      <div className="page-head">
        <div>
          {!self && <div className="crumbs"><Link href="/researchers">Researchers</Link> /</div>}
          <h1>{researcherName(r)}</h1>
          <p>
            {[fac?.name, dep?.name, r.staff_number && `Staff no. ${r.staff_number}`, r.employment_status.replace("_", " ")]
              .filter(Boolean).join(" · ")}
          </p>
        </div>
        {admin && (
          <ActionForm action={startDiscovery} hidden={{ researcher_id: r.id }}>
            <SubmitButton>Run discovery</SubmitButton>
          </ActionForm>
        )}
      </div>

      <div className="tiles">
        <Link className="tile" href="/queue"><div className="tile-label">Awaiting authorship review</div><div className="tile-value">{counts.candidate}</div></Link>
        <div className="tile"><div className="tile-label">Confirmed publications</div><div className="tile-value">{counts.confirmed}</div></div>
        <div className="tile"><div className="tile-label">Confirmed FU output</div><div className="tile-value">{counts.fu}</div></div>
      </div>

      {pending.length > 0 && canEditNames && (
        <section className="card" style={{ marginBottom: 16, borderColor: "var(--warn)" }}>
          <h2>Names found on {self ? "your" : "this researcher's"} publications</h2>
          <p className="small muted" style={{ marginBottom: 10 }}>
            These bylines appeared on publications matched through a verified identifier. {self ? "Confirm the ones you have published under" : "Confirm the ones this researcher has published under"};
            confirmed names are searched in the next discovery run.
          </p>
          <div className="stack">
            {pending.map((v) => (
              <ActionForm key={v.id} action={reviewVariant} hidden={{ variant_id: v.id }} className="row">
                <strong style={{ minWidth: 180 }}>{v.variant_name}</strong>
                <SubmitButton name="confirmation_status" value="confirmed" variant="secondary">{self ? "I use this name" : "Confirm name"}</SubmitButton>
                <SubmitButton name="confirmation_status" value="rejected" variant="danger">{self ? "Not me" : "Reject"}</SubmitButton>
              </ActionForm>
            ))}
          </div>
        </section>
      )}

      <div className="grid-main">
        <div className="stack">
          <section className="card">
            <div className="card-head">
              <h2>Publications</h2>
              <span className="small muted">{matches.length} linked</span>
            </div>
            {matches.length === 0 ? (
              <p className="empty">No publications found yet. {admin ? "Run discovery to search the scholarly sources." : ""}</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Publication</th><th>Year</th><th>Status</th></tr></thead>
                  <tbody>
                    {matches.map(({ match: m, publication: p, attribution: a }) => (
                      <tr key={m.id}>
                        <td style={{ minWidth: 260 }}>
                          <Link href={`/publications/${p.id}`}>{p.title}</Link>
                          {p.journal_name && <div className="small muted">{p.journal_name}</div>}
                        </td>
                        <td>{p.publication_year ?? "—"}</td>
                        <td>
                          <div className="stack" style={{ gap: 4 }}>
                            {m.match_status === "candidate" ? <ConfidenceBadge c={m.confidence} /> : <MatchStatusBadge s={m.match_status} />}
                            {m.match_status !== "rejected" && <AttributionBadge a={a} />}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="card">
            <div className="card-head">
              <h2>Latest discovery run</h2>
              {runs[0] && <span className="small muted">{fmtDateTime(runs[0].started_at)}</span>}
            </div>
            {latestRuns.length === 0 ? (
              <p className="muted small">Discovery has not run for this researcher.</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Source</th><th>Query</th><th className="num">Found</th><th className="num">New</th><th className="num">Matched</th><th>Status</th></tr></thead>
                  <tbody>
                    {latestRuns.map((x) => (
                      <tr key={x.id}>
                        <td>{x.source_name}</td>
                        <td>
                          <span className="small muted">{x.query_type.replaceAll("_", " ")}: </span>
                          <span className="mono">{x.search_query}</span>
                          {x.error_message && <div className="small" style={{ color: "var(--bad)" }}>{x.error_message}</div>}
                        </td>
                        <td className="num">{x.records_found}</td>
                        <td className="num">{x.unique_records_found}</td>
                        <td className="num">{x.candidates_matched}</td>
                        <td><RunStatusBadge s={x.run_status} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>

        <div className="stack">
          <section className="card">
            <h2>Identifiers</h2>
            {r.identifiers.length === 0 && <p className="muted small">No identifiers recorded. A verified ORCID is the strongest evidence for matching.</p>}
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }} className="stack">
              {r.identifiers.map((i) => (
                <li key={i.id} className="row" style={{ justifyContent: "space-between" }}>
                  <div>
                    <div className="small muted">{ID_LABEL[i.identifier_type] ?? i.identifier_type}</div>
                    <div className="mono">{i.identifier_value}</div>
                  </div>
                  {i.verified ? (
                    <span className="badge badge-good">Verified</span>
                  ) : admin ? (
                    <ActionForm action={verifyIdentifier} hidden={{ identifier_id: i.id }}>
                      <SubmitButton variant="secondary">Mark verified</SubmitButton>
                    </ActionForm>
                  ) : (
                    <span className="badge badge-warn">Unverified</span>
                  )}
                </li>
              ))}
            </ul>
            {canEditNames && (
              <details style={{ marginTop: 14 }}>
                <summary>Add an identifier</summary>
                <ActionForm action={addIdentifier} hidden={{ researcher_id: r.id }}>
                  <div className="form-grid">
                    <label>
                      Type
                      <select name="identifier_type" defaultValue="orcid">
                        {Object.entries(ID_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                      </select>
                    </label>
                    <label>Value<input type="text" name="identifier_value" required placeholder="0000-0000-0000-0000" /></label>
                  </div>
                  {admin && <label className="check" style={{ marginTop: 8 }}><input type="checkbox" name="verified" /> Verified against the source</label>}
                  <div className="form-actions"><SubmitButton variant="secondary">Add identifier</SubmitButton></div>
                </ActionForm>
              </details>
            )}
          </section>

          <section className="card">
            <h2>Employment history</h2>
            {r.employment.length === 0 ? (
              <p className="muted small">No employment periods. Attribution cannot be assessed without them.</p>
            ) : (
              <ul style={{ listStyle: "none", padding: 0, margin: 0 }} className="stack">
                {r.employment.map((e) => (
                  <li key={e.id}>
                    <div style={{ fontWeight: 550 }}>{e.institution_name}{e.is_fountain_university && <span className="badge plain badge-info" style={{ marginLeft: 6 }}>FU</span>}</div>
                    <div className="small muted">
                      {fmtDate(e.start_date)} – {e.end_date ? fmtDate(e.end_date) : "present"}
                      {e.employment_type && ` · ${e.employment_type}`} · {e.verification_status}
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {admin && (
              <details style={{ marginTop: 14 }}>
                <summary>Add an employment period</summary>
                <ActionForm action={addEmployment} hidden={{ researcher_id: r.id }}>
                  <div className="form-grid">
                    <label style={{ gridColumn: "1 / -1" }}>Institution<input type="text" name="institution_name" required defaultValue="Fountain University, Osogbo" /></label>
                    <label>Start<input type="date" name="start_date" /></label>
                    <label>End (blank if current)<input type="date" name="end_date" /></label>
                    <label>Type<input type="text" name="employment_type" placeholder="full-time, joint…" /></label>
                    <label>Evidence<input type="text" name="evidence_reference" placeholder="HR letter ref." /></label>
                  </div>
                  <label className="check" style={{ marginTop: 8 }}><input type="checkbox" name="is_fountain_university" defaultChecked /> Fountain University appointment</label>
                  <div className="form-actions"><SubmitButton variant="secondary">Add period</SubmitButton></div>
                </ActionForm>
              </details>
            )}
          </section>

          <section className="card">
            <h2>Name variants</h2>
            <p className="small muted" style={{ marginBottom: 8 }}>Confirmed names are searched in every discovery run.</p>
            <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 6 }}>
              {otherVariants.map((v) => (
                <li key={v.id} className="row" style={{ justifyContent: "space-between" }}>
                  <span>{v.variant_name}</span>
                  <span className={`badge plain ${v.confirmation_status === "rejected" ? "badge-bad" : v.variant_type === "researcher_confirmed" ? "badge-info" : ""}`}>
                    {v.confirmation_status === "rejected" ? "Rejected" : VARIANT_LABEL[v.variant_type]}
                  </span>
                </li>
              ))}
            </ul>
            {canEditNames && (
              <details style={{ marginTop: 14 }}>
                <summary>Add a name used in publications</summary>
                <ActionForm action={addAlias} hidden={{ researcher_id: r.id }}>
                  <label>Name as it appears on papers<input type="text" name="variant_name" required placeholder="e.g. Basit A. Ajibade" /></label>
                  <div className="form-actions"><SubmitButton variant="secondary">Add confirmed name</SubmitButton></div>
                </ActionForm>
              </details>
            )}
          </section>
        </div>
      </div>
    </>
  );
}
