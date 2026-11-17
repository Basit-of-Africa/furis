import Link from "next/link";

import { Unavailable } from "@/components/unavailable";
import { qs } from "@/lib/api";
import { publicGet, type PublicResearcher } from "@/lib/public";

export const metadata = { title: "Researchers" };
export const dynamic = "force-dynamic";

export default async function PublicResearchers({ searchParams }: { searchParams: Promise<{ q?: string; faculty_id?: string }> }) {
  const sp = await searchParams;
  const [people, faculties] = await Promise.all([
    publicGet<PublicResearcher[]>(`/researchers${qs({ q: sp.q?.slice(0, 200), faculty_id: sp.faculty_id })}`),
    publicGet<{ id: string; name: string }[]>("/faculties"),
  ]);
  if (!people) return <Unavailable />;
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Researchers</h1>
          <p>Fountain University researchers with publications confirmed by the Research Desk.</p>
        </div>
      </div>
      <form className="filters" method="get">
        <label style={{ minWidth: 240 }}>
          Name
          <input type="search" name="q" defaultValue={sp.q ?? ""} />
        </label>
        {faculties && faculties.length > 0 && (
          <label>
            Faculty
            <select name="faculty_id" defaultValue={sp.faculty_id ?? ""}>
              <option value="">All faculties</option>
              {faculties.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
            </select>
          </label>
        )}
        <button className="btn btn-secondary" type="submit">Search</button>
      </form>
      <section className="card">
        {people.length === 0 ? (
          <p className="empty">No researchers found. Researchers appear here once the Research Desk confirms a publication.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Researcher</th><th>Faculty / department</th><th className="num">Publications</th><th className="num">FU output</th></tr></thead>
              <tbody>
                {people.map((r) => (
                  <tr key={r.id}>
                    <td><Link href={`/researchers/${r.id}`}>{r.name}</Link></td>
                    <td>{[r.faculty, r.department].filter(Boolean).join(" · ") || "—"}</td>
                    <td className="num">{r.publication_count}</td>
                    <td className="num">{r.fu_output_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
