import Link from "next/link";
import { notFound } from "next/navigation";

import { PublicPublicationItem } from "@/components/public-publication";
import { publicGet, type PublicResearcherDetail } from "@/lib/public";

export const metadata = { title: "Researcher" };
export const dynamic = "force-dynamic";

export default async function PublicResearcherPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^[0-9a-f-]{32,36}$/i.test(id)) notFound();
  const r = await publicGet<PublicResearcherDetail>(`/researchers/${id}`);
  if (!r) notFound();
  const fu = r.publications.filter((p) => p.fu_output);
  const other = r.publications.filter((p) => !p.fu_output);
  return (
    <>
      <div className="page-head">
        <div>
          <div className="crumbs"><Link href="/researchers">Researchers</Link> /</div>
          <h1>{r.name}</h1>
          <p>
            {[r.faculty, r.department].filter(Boolean).join(" · ")}
            {r.orcid && (
              <>
                {(r.faculty || r.department) && " · "}ORCID{" "}
                <a href={`https://orcid.org/${r.orcid}`} target="_blank" rel="noopener noreferrer" className="mono">{r.orcid}</a>
              </>
            )}
          </p>
        </div>
      </div>
      <div className="tiles">
        <div className="tile"><div className="tile-label">Confirmed publications</div><div className="tile-value">{r.publication_count}</div></div>
        <div className="tile"><div className="tile-label">Fountain University output</div><div className="tile-value">{r.fu_output_count}</div></div>
      </div>
      <section className="card" style={{ marginBottom: 16 }}>
        <h2>Fountain University output</h2>
        {fu.length ? <ul className="pub-list">{fu.map((p) => <PublicPublicationItem key={p.id} p={p} hideResearcher={r.id} />)}</ul>
          : <p className="muted small">None confirmed yet.</p>}
      </section>
      {other.length > 0 && (
        <section className="card">
          <h2>Other publications</h2>
          <p className="small muted" style={{ marginBottom: 8 }}>
            Confirmed as this researcher&apos;s work but not counted as Fountain University output, for example work
            published before joining the university.
          </p>
          <ul className="pub-list">{other.map((p) => <PublicPublicationItem key={p.id} p={p} hideResearcher={r.id} />)}</ul>
        </section>
      )}
    </>
  );
}
