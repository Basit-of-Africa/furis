import Link from "next/link";
import { redirect } from "next/navigation";

import { RunStatusBadge } from "@/components/badges";
import { YearChart } from "@/components/year-chart";
import { apiGet, getMe } from "@/lib/api";
import type { Faculty, Summary } from "@/lib/types";

export const metadata = { title: "Dashboard" };

export default async function Dashboard() {
  const me = await getMe();
  if (me.role === "researcher") redirect("/queue");
  const [s, faculties] = await Promise.all([apiGet<Summary>("/analytics/summary"), apiGet<Faculty[]>("/faculties")]);
  const facName = new Map(faculties.map((f) => [f.id, f.name]));
  const years = s.fu_output_by_year.map((r) => ({ year: r.year === null ? "Unknown" : String(r.year), count: r.count }));

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Research output</h1>
          <p>
            Institutional output counts only publications a Research Office reviewer has confirmed. Discovered and
            suggested records are shown separately until they are verified.
          </p>
        </div>
      </div>

      <div className="tiles">
        <div className="tile">
          <div className="tile-label">Confirmed FU output</div>
          <div className="tile-value">{s.confirmed_fu_output}</div>
          <div className="tile-note">Reviewed and approved</div>
        </div>
        <div className="tile">
          <div className="tile-label">Confirmed researcher publications</div>
          <div className="tile-value">{s.confirmed_researcher_publications}</div>
          <div className="tile-note">Authorship verified</div>
        </div>
        <Link className="tile" href="/queue">
          <div className="tile-label">Awaiting authorship review</div>
          <div className="tile-value">{s.awaiting_authorship_review}</div>
          <div className="tile-note">Open the review queue →</div>
        </Link>
        <div className="tile">
          <div className="tile-label">Awaiting attribution decision</div>
          <div className="tile-value">{s.awaiting_attribution_review}</div>
          <div className="tile-note">No final status yet</div>
        </div>
        <div className="tile">
          <div className="tile-label">Publications discovered</div>
          <div className="tile-value">{s.publications_discovered}</div>
          <div className="tile-note">Across {s.researchers} researchers</div>
        </div>
      </div>

      <div className="grid-main">
        <section className="card">
          <div className="card-head">
            <h2>Confirmed FU output by publication year</h2>
          </div>
          {years.length ? (
            <>
              <YearChart data={years} />
              <details style={{ marginTop: 12 }}>
                <summary>Show as table</summary>
                <table>
                  <thead><tr><th>Year</th><th className="num">Publications</th></tr></thead>
                  <tbody>{years.map((r) => <tr key={r.year}><td>{r.year}</td><td className="num">{r.count}</td></tr>)}</tbody>
                </table>
              </details>
            </>
          ) : (
            <p className="empty">No publications have been confirmed as FU output yet.</p>
          )}
        </section>

        <div className="stack">
          <section className="card">
            <h2>Research visibility</h2>
            <dl className="kv">
              <dt>Verified ORCID</dt><dd>{s.pct_researchers_verified_orcid}% of researchers</dd>
              <dt>Confirmed publications</dt><dd>{s.pct_researchers_with_confirmed_publications}% of researchers</dd>
            </dl>
          </section>
          <section className="card">
            <h2>FU output by faculty</h2>
            {s.fu_output_by_faculty.length ? (
              <table>
                <tbody>
                  {s.fu_output_by_faculty.map((f) => (
                    <tr key={f.faculty_id ?? "none"}>
                      <td>{f.faculty_id ? facName.get(f.faculty_id) ?? "Unknown faculty" : "No faculty recorded"}</td>
                      <td className="num">{f.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <p className="muted small">None confirmed yet.</p>}
          </section>
          <section className="card">
            <h2>Search runs</h2>
            {Object.keys(s.search_runs_by_status).length ? (
              <table>
                <tbody>
                  {Object.entries(s.search_runs_by_status).map(([k, v]) => (
                    <tr key={k}><td><RunStatusBadge s={k} /></td><td className="num">{v}</td></tr>
                  ))}
                </tbody>
              </table>
            ) : <p className="muted small">No discovery has run yet.</p>}
          </section>
        </div>
      </div>
    </>
  );
}
