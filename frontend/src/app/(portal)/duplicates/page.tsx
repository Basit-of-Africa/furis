import { redirect } from "next/navigation";

import { decideDuplicate } from "@/app/actions";
import { ActionForm, SubmitButton } from "@/components/forms";
import { PublicationMeta } from "@/components/publication-meta";
import { apiGet, getMe } from "@/lib/api";
import { isAdmin } from "@/lib/format";
import type { Duplicate, Publication } from "@/lib/types";
import Link from "next/link";

export const metadata = { title: "Possible duplicates" };

function Side({ p, label }: { p: Publication | null; label: string }) {
  return (
    <div className="dup-side">
      <div className="section-label">{label}</div>
      {p ? (
        <>
          <div style={{ fontWeight: 600 }}><Link href={`/publications/${p.id}`}>{p.title}</Link></div>
          <PublicationMeta p={p} />
          {!p.doi && <div className="small muted">No DOI</div>}
        </>
      ) : <span className="muted">Record no longer exists</span>}
    </div>
  );
}

export default async function DuplicatesPage() {
  const me = await getMe();
  if (!isAdmin(me.role)) redirect("/");
  const dups = await apiGet<Duplicate[]>("/duplicates");
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Possible duplicates</h1>
          <p>
            Records with very similar titles that could not be confirmed by DOI. FURIS never merges these automatically.
            Merging keeps the DOI-bearing record and moves every source, match and decision onto it.
          </p>
        </div>
      </div>
      <div className="stack">
        {dups.length === 0 && <div className="card empty">No possible duplicates are waiting for review.</div>}
        {dups.map((d) => (
          <article className="item" key={d.id}>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <span className="small muted">{d.reason}</span>
              <span className="badge plain">Title similarity {Math.round(d.similarity)}%</span>
            </div>
            <div className="dup-pair">
              <Side p={d.publication} label="Record A" />
              <Side p={d.other_publication} label="Record B" />
            </div>
            <ActionForm action={decideDuplicate} hidden={{ duplicate_id: d.id }}>
              <div className="form-actions">
                <SubmitButton name="status" value="merged">Same publication: merge</SubmitButton>
                <SubmitButton name="status" value="distinct" variant="secondary">Different publications</SubmitButton>
              </div>
            </ActionForm>
          </article>
        ))}
      </div>
    </>
  );
}
