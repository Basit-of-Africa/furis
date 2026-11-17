import Link from "next/link";

import { PublicPublicationItem } from "@/components/public-publication";
import { Unavailable } from "@/components/unavailable";
import { YearChart } from "@/components/year-chart";
import { publicGet, type PublicPublication, type PublicSummary } from "@/lib/public";

export const metadata = { title: "Fountain University research" };
export const dynamic = "force-dynamic";

export default async function PublicHome() {
  const [s, recent] = await Promise.all([
    publicGet<PublicSummary>("/summary"),
    publicGet<PublicPublication[]>("/publications?scope=fu&limit=8"),
  ]);
  if (!s) return <Unavailable />;
  const years = s.fu_output_by_year.map((r) => ({ year: r.year === null ? "Unknown" : String(r.year), count: r.count }));
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Research at Fountain University</h1>
          <p>Publications by Fountain University researchers, confirmed by the university&apos;s Research Desk.</p>
        </div>
      </div>
      <div className="tiles">
        <Link className="tile" href="/publications">
          <div className="tile-label">Fountain University output</div>
          <div className="tile-value">{s.fu_output}</div>
          <div className="tile-note">Confirmed publications →</div>
        </Link>
        <Link className="tile" href="/researchers">
          <div className="tile-label">Researchers</div>
          <div className="tile-value">{s.researchers}</div>
          <div className="tile-note">With confirmed publications →</div>
        </Link>
        <Link className="tile" href="/publications?scope=all">
          <div className="tile-label">All researcher publications</div>
          <div className="tile-value">{s.researcher_publications}</div>
          <div className="tile-note">Including work from before joining FU →</div>
        </Link>
      </div>

      <div className="grid-main">
        <section className="card">
          <h2>Recent Fountain University output</h2>
          {recent && recent.length ? (
            <ul className="pub-list">{recent.map((p) => <PublicPublicationItem key={p.id} p={p} />)}</ul>
          ) : (
            <p className="empty">No publications have been confirmed yet.</p>
          )}
          {recent && recent.length > 0 && <p style={{ marginTop: 12 }}><Link href="/publications">All publications →</Link></p>}
        </section>
        <div className="stack">
          <section className="card">
            <h2>Output by publication year</h2>
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
            ) : <p className="muted small">Nothing confirmed yet.</p>}
          </section>
          <section className="card">
            <h2>By faculty</h2>
            {s.faculties.length ? (
              <table>
                <tbody>
                  {s.faculties.map((f) => (
                    <tr key={f.id}>
                      <td><Link href={`/publications?faculty_id=${f.id}`}>{f.name}</Link></td>
                      <td className="num">{f.fu_output}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <p className="muted small">Nothing confirmed yet.</p>}
          </section>
        </div>
      </div>
    </>
  );
}
