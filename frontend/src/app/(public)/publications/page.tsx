import Link from "next/link";

import { Unavailable } from "@/components/unavailable";
import { PublicPublicationItem } from "@/components/public-publication";
import { qs } from "@/lib/api";
import { publicGet, type PublicPublication } from "@/lib/public";

export const metadata = { title: "Publications" };
export const dynamic = "force-dynamic";

type Search = Promise<{ scope?: string; year?: string; faculty_id?: string; q?: string; page?: string }>;
const PAGE = 30;

export default async function PublicPublications({ searchParams }: { searchParams: Search }) {
  const sp = await searchParams;
  const scope = sp.scope === "all" ? "all" : "fu";
  const page = Math.max(1, Number(sp.page) || 1);
  const year = /^\d{4}$/.test(sp.year ?? "") ? sp.year : undefined;
  const filters = { scope, year, faculty_id: sp.faculty_id, q: sp.q?.slice(0, 200) };
  const [pubs, faculties] = await Promise.all([
    publicGet<PublicPublication[]>(`/publications${qs({ ...filters, limit: PAGE + 1, offset: (page - 1) * PAGE })}`),
    publicGet<{ id: string; name: string }[]>("/faculties"),
  ]);
  if (!pubs) return <Unavailable />;
  const more = pubs.length > PAGE;
  const link = (p: number) => `/publications${qs({ ...filters, page: p })}`;
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Publications</h1>
          <p>
            {scope === "fu"
              ? "Research confirmed as Fountain University output."
              : "Every confirmed publication by Fountain University researchers, including work from before they joined."}
          </p>
        </div>
      </div>
      <form className="filters" method="get">
        <label>
          Show
          <select name="scope" defaultValue={scope}>
            <option value="fu">Fountain University output</option>
            <option value="all">All researcher publications</option>
          </select>
        </label>
        <label style={{ minWidth: 220 }}>
          Search
          <input type="search" name="q" defaultValue={sp.q ?? ""} placeholder="Title, journal or researcher" />
        </label>
        <label style={{ minWidth: 100 }}>
          Year
          <input type="number" name="year" min={1900} max={2100} defaultValue={year ?? ""} />
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
        <button className="btn btn-secondary" type="submit">Apply</button>
      </form>
      <section className="card">
        {pubs.length === 0 ? (
          <p className="empty">No publications match.</p>
        ) : (
          <ul className="pub-list">{pubs.slice(0, PAGE).map((p) => <PublicPublicationItem key={p.id} p={p} />)}</ul>
        )}
      </section>
      {(page > 1 || more) && (
        <div className="row" style={{ marginTop: 16 }}>
          {page > 1 && <Link className="btn btn-secondary" href={link(page - 1)}>← Previous</Link>}
          <span className="muted small">Page {page}</span>
          {more && <Link className="btn btn-secondary" href={link(page + 1)}>Next →</Link>}
        </div>
      )}
    </>
  );
}
