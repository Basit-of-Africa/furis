import Link from "next/link";

import { ReviewItem } from "@/components/review-item";
import { apiGet, getMe, qs } from "@/lib/api";
import { isAdmin } from "@/lib/format";
import type { QueueItem } from "@/lib/types";

export const metadata = { title: "Review queue" };

type Search = Promise<{ tab?: string; confidence?: string; page?: string }>;
const PAGE = 25;

export default async function QueuePage({ searchParams }: { searchParams: Search }) {
  const sp = await searchParams;
  const me = await getMe();
  const admin = isAdmin(me.role);
  const tab = admin && sp.tab === "attribution" ? "attribution" : "authorship";
  const page = Math.max(1, Number(sp.page) || 1);
  const canDecideAuthorship = admin || me.role === "researcher";

  const items =
    tab === "attribution"
      ? await apiGet<QueueItem[]>(`/verification/attribution-queue${qs({ limit: PAGE + 1, offset: (page - 1) * PAGE })}`)
      : await apiGet<QueueItem[]>(
          `/verification/queue${qs({ confidence: sp.confidence, limit: PAGE + 1, offset: (page - 1) * PAGE })}`,
        );
  const more = items.length > PAGE;
  const shown = items.slice(0, PAGE);
  const link = (o: Record<string, string | number | undefined>) =>
    `/desk/queue${qs({ tab: tab === "attribution" ? tab : undefined, confidence: sp.confidence, ...o })}`;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{me.role === "researcher" ? "Is this your publication?" : "Review queue"}</h1>
          <p>
            {tab === "authorship"
              ? "Confirm or reject each candidate. Confirming authorship does not count the paper as Fountain University output; that is a separate Research Office decision."
              : "These publications have confirmed authors. Decide whether each one counts as Fountain University output under the attribution policy."}
          </p>
        </div>
      </div>

      {admin && (
        <div className="row" style={{ marginBottom: 14 }}>
          <Link aria-current={tab === "authorship" ? "page" : undefined}
                className={`btn ${tab === "authorship" ? "btn-primary" : "btn-secondary"}`} href="/desk/queue">
            Authorship
          </Link>
          <Link aria-current={tab === "attribution" ? "page" : undefined}
                className={`btn ${tab === "attribution" ? "btn-primary" : "btn-secondary"}`} href="/desk/queue?tab=attribution">
            Attribution
          </Link>
        </div>
      )}

      {tab === "authorship" && (
        <form className="filters" method="get">
          <label>
            Confidence
            <select name="confidence" defaultValue={sp.confidence ?? ""}>
              <option value="">All (highest first)</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </label>
          <button className="btn btn-secondary" type="submit">Filter</button>
        </form>
      )}

      <div className="stack">
        {shown.length === 0 && (
          <div className="card empty">
            {tab === "authorship"
              ? "Nothing is waiting for authorship review."
              : "No confirmed publication is waiting for an attribution decision."}
          </div>
        )}
        {shown.map((it) => (
          <ReviewItem
            key={it.match.id}
            item={it}
            showResearcher={me.role !== "researcher"}
            mode={tab === "attribution" ? "attribution" : canDecideAuthorship ? "authorship" : "readonly"}
          />
        ))}
      </div>

      {(page > 1 || more) && (
        <div className="row" style={{ marginTop: 16 }}>
          {page > 1 && <Link className="btn btn-secondary" href={link({ page: page - 1 })}>← Previous</Link>}
          <span className="muted small">Page {page}</span>
          {more && <Link className="btn btn-secondary" href={link({ page: page + 1 })}>Next →</Link>}
        </div>
      )}
    </>
  );
}
