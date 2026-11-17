import { doiUrl, safeUrl } from "@/lib/format";
import type { Publication } from "@/lib/types";

/** Year · journal · DOI line. All values are external metadata, rendered as escaped text. */
export function PublicationMeta({ p }: { p: Publication }) {
  const doi = doiUrl(p.doi);
  const landing = !doi ? safeUrl(p.landing_page_url) : null;
  const parts = [p.publication_year ?? "Year unknown", p.journal_name, p.document_type].filter(Boolean);
  return (
    <div className="item-meta">
      {parts.join(" · ")}
      {doi && (
        <>
          {" · "}
          <a href={doi} target="_blank" rel="noopener noreferrer nofollow" className="mono">
            {p.doi}
          </a>
        </>
      )}
      {landing && (
        <>
          {" · "}
          <a href={landing} target="_blank" rel="noopener noreferrer nofollow">Publisher page</a>
        </>
      )}
      {p.is_open_access && <> · <span className="badge plain badge-info">Open access</span></>}
    </div>
  );
}
