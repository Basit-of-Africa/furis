import Link from "next/link";

import { PublicationMeta } from "@/components/publication-meta";
import { apiGet, qs } from "@/lib/api";
import { ATTRIBUTION_LABEL, MATCH_STATUS_LABEL } from "@/lib/format";
import type { AttributionStatus, MatchStatus, Publication } from "@/lib/types";

export const metadata = { title: "Publications" };

type Search = Promise<{ match_status?: string; attribution_status?: string; year?: string; page?: string }>;
const PAGE = 50;

export default async function PublicationsPage({ searchParams }: { searchParams: Search }) {
  const sp = await searchParams;
  const page = Math.max(1, Number(sp.page) || 1);
  const filters = { match_status: sp.match_status, attribution_status: sp.attribution_status, year: sp.year };
  const pubs = await apiGet<Publication[]>(`/publications${qs({ ...filters, limit: PAGE + 1, offset: (page - 1) * PAGE })}`);
  const more = pubs.length > PAGE;
  const link = (p: number) => `/publications${qs({ ...filters, page: p })}`;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Publications</h1>
          <p>
            Every publication linked to a researcher, whatever its review state. The attribution filter uses the
            reviewed status where one exists and the system suggestion otherwise.
          </p>
        </div>
      </div>

      <form className="filters" method="get">
        <label>
          Authorship
          <select name="match_status" defaultValue={sp.match_status ?? ""}>
            <option value="">Any</option>
            {(Object.keys(MATCH_STATUS_LABEL) as MatchStatus[]).map((k) => (
              <option key={k} value={k}>{MATCH_STATUS_LABEL[k]}</option>
            ))}
          </select>
        </label>
        <label>
          Attribution
          <select name="attribution_status" defaultValue={sp.attribution_status ?? ""}>
            <option value="">Any</option>
            {(Object.keys(ATTRIBUTION_LABEL) as AttributionStatus[]).map((k) => (
              <option key={k} value={k}>{ATTRIBUTION_LABEL[k]}</option>
            ))}
          </select>
        </label>
        <label style={{ minWidth: 110 }}>
          Year
          <input type="number" name="year" min={1900} max={2100} defaultValue={sp.year ?? ""} />
        </label>
        <button className="btn btn-secondary" type="submit">Filter</button>
        {(sp.match_status || sp.attribution_status || sp.year) && <Link className="btn btn-secondary" href="/publications">Clear</Link>}
      </form>

      <section className="card">
        {pubs.length === 0 ? (
          <p className="empty">No publications match these filters.</p>
        ) : (
          <ul style={{ listStyle: "none", margin: 0, padding: 0 }} className="stack">
            {pubs.slice(0, PAGE).map((p) => (
              <li key={p.id} style={{ borderBottom: "1px solid var(--border)", paddingBottom: 12 }}>
                <div className="item-title"><Link href={`/publications/${p.id}`}>{p.title}</Link></div>
                <PublicationMeta p={p} />
              </li>
            ))}
          </ul>
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
