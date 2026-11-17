import Link from "next/link";

import { doiUrl, safeUrl } from "@/lib/format";
import type { PublicPublication } from "@/lib/public";

export function PublicPublicationItem({ p, hideResearcher }: { p: PublicPublication; hideResearcher?: string }) {
  const doi = doiUrl(p.doi);
  const link = doi ?? safeUrl(p.landing_page_url);
  const people = p.researchers.filter((r) => r.id !== hideResearcher);
  return (
    <li className="pub">
      <div className="item-title">
        {link ? <a href={link} target="_blank" rel="noopener noreferrer nofollow">{p.title}</a> : p.title}
      </div>
      <div className="item-meta">
        {[p.publication_year ?? "Year unknown", p.journal_name].filter(Boolean).join(" · ")}
        {p.doi && <> · <span className="mono">{p.doi}</span></>}
      </div>
      {people.length > 0 && (
        <div className="item-meta">
          {people.map((r, i) => (
            <span key={r.id}>{i > 0 && ", "}<Link href={`/researchers/${r.id}`}>{r.name}</Link></span>
          ))}
        </div>
      )}
      <div className="row" style={{ marginTop: 6 }}>
        {p.fu_output && <span className="badge badge-good">Fountain University output</span>}
        {p.is_open_access && <span className="badge plain badge-info">Open access</span>}
      </div>
    </li>
  );
}
