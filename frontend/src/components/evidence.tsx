import { methodLabel } from "@/lib/format";
import type { Attribution, Match } from "@/lib/types";

/** Why the engine proposed this match, de-duplicated across sources. */
export function MatchEvidence({ m }: { m: Match }) {
  const sources = m.evidence_summary.sources ?? [];
  const bylines = new Map<string, Set<string>>();
  const signals = new Set<string>();
  const warnings = new Set<string>();
  for (const e of sources) {
    if (e.raw_name) {
      const set = bylines.get(e.raw_name) ?? new Set<string>();
      if (e.source) set.add(e.source);
      bylines.set(e.raw_name, set);
    }
    e.signals?.forEach((x) => signals.add(x));
    if (e.warning === "identifier_name_inconsistency") warnings.add("The identifier matches, but the byline name does not fit this researcher. Check for a contaminated profile.");
  }
  const via = [...new Set(sources.map((e) => e.source).filter(Boolean))];
  return (
    <div>
      <div className="section-label">Authorship evidence</div>
      <ul className="evidence">
        <li>{methodLabel(m.matching_method)}{via.length ? ` (via ${via.join(", ")})` : ""}</li>
        {[...bylines].map(([name, srcs]) => (
          <li key={name}>Byline <strong>“{name}”</strong>{srcs.size ? ` in ${[...srcs].join(", ")}` : ""}</li>
        ))}
        {[...signals].map((x) => <li key={x}>{x}</li>)}
        {[...warnings].map((x) => <li key={x} style={{ color: "var(--bad)" }}>Warning: {x}</li>)}
      </ul>
    </div>
  );
}

export function AttributionEvidence({ a }: { a: Attribution | null }) {
  if (!a) return <p className="small muted">Not assessed yet.</p>;
  const ev = a.evidence ?? {};
  return (
    <div>
      <div className="section-label">Attribution evidence</div>
      <ul className="evidence">
        {(ev.reasons ?? []).map((r) => <li key={r}>{r[0].toUpperCase() + r.slice(1)}</li>)}
        <li>FU affiliation in metadata: {ev.fu_affiliation_in_metadata ? "yes" : "no"}</li>
        {ev.other_affiliations?.length ? <li>Other affiliations: {ev.other_affiliations.join("; ")}</li> : null}
        <li className="muted">Policy {a.policy_version}</li>
      </ul>
    </div>
  );
}
