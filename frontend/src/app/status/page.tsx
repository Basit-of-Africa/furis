import type { Metadata } from "next";

import { API_BASE } from "@/lib/session";

export const metadata: Metadata = { title: "System status" };
export const dynamic = "force-dynamic";

type Check = { name: string; ok: boolean; detail: string };

async function probe(path: string): Promise<{ status: number; json: unknown; type: string } | { error: string }> {
  try {
    const res = await fetch(`${API_BASE}${path}`, { cache: "no-store", signal: AbortSignal.timeout(10000) });
    const type = res.headers.get("content-type") ?? "";
    const json = type.includes("application/json") ? await res.json().catch(() => null) : null;
    return { status: res.status, json, type };
  } catch (e) {
    return { error: (e as Error).message };
  }
}

/** Plain-language diagnostics for deployment problems. Shows no secrets or personal data. */
export default async function StatusPage() {
  const checks: Check[] = [];
  const configured = Boolean(process.env.FURIS_API_URL);
  let host = API_BASE;
  try {
    const u = new URL(API_BASE);
    host = `${u.protocol}//${u.host}`;
  } catch {
    /* invalid URL, reported below */
  }
  checks.push({
    name: "API address (FURIS_API_URL)",
    ok: configured && /^https?:\/\/[^/]+/.test(API_BASE) && !/localhost|127\.0\.0\.1/.test(API_BASE),
    detail: !configured
      ? "Not set on this project, so the default http://localhost:8000 is used, which doesn't exist on Vercel. Set FURIS_API_URL to the backend's address (https://…) and redeploy."
      : !/^https?:\/\//.test(API_BASE)
        ? `"${API_BASE}" must start with https://. Fix FURIS_API_URL and redeploy.`
        : `${host}`,
  });

  const health = await probe("/health");
  if ("error" in health) {
    checks.push({ name: "API reachable", ok: false, detail: `Could not connect (${health.error}). Check the address, and that the backend deployment succeeded.` });
  } else {
    const h = health.json as { status?: string; database?: string; schema?: string | null } | null;
    const isFuris = health.status === 200 && h?.status === "ok";
    checks.push({
      name: "API reachable",
      ok: isFuris,
      detail: isFuris
        ? "Yes"
        : health.status === 401 || health.status === 403
          ? `Refused (${health.status}). On Vercel, turn off Deployment Protection for the backend project, or check that FURIS_API_URL is its production address.`
          : !health.type.includes("application/json")
            ? `Got a ${health.status} web page instead of the FURIS API. FURIS_API_URL probably points to the wrong project.`
            : health.status >= 500
              ? `Backend error (${health.status}). Open the backend project's logs on Vercel; a startup setting is usually missing.`
              : `Unexpected response (${health.status}).`,
    });
    if (isFuris) {
      checks.push({
        name: "Database",
        ok: h?.database === "ok",
        detail: h?.database === "ok" ? "Connected" : "The backend can't reach the database. Check the Neon integration on the backend project (DATABASE_URL).",
      });
      checks.push({
        name: "Database tables",
        ok: Boolean(h?.schema),
        detail: h?.schema ? `Created (migration ${h.schema})` : "Not created yet. Run the “Database migrations” workflow in GitHub Actions.",
      });
    }
  }

  const cfg = await probe("/auth/config");
  if (!("error" in cfg) && cfg.status === 200) {
    const mode = (cfg.json as { mode?: string } | null)?.mode;
    checks.push({ name: "Sign-in mode", ok: mode === "password" || mode === "oidc", detail: mode ?? "unknown" });
  }
  const pub = await probe("/public/summary");
  if (!("error" in pub)) {
    checks.push({
      name: "Public research view",
      ok: pub.status === 200,
      detail: pub.status === 200 ? "Working" : pub.status === 404 && pub.type.includes("json") ? "Switched off (FURIS_PUBLIC_VIEW=false)"
        : pub.status >= 500 ? `Backend error (${pub.status}); usually the database tables are missing.` : `Status ${pub.status}`,
    });
  }

  const allOk = checks.every((c) => c.ok);
  return (
    <main className="login-wrap">
      <div className="card stack" style={{ width: "100%", maxWidth: 640 }}>
        <h1>FURIS system status</h1>
        <p className={allOk ? "notice notice-ok" : "notice notice-error"} style={{ marginTop: 0 }}>
          {allOk ? "Everything is working." : "Something needs attention; see below."}
        </p>
        <table>
          <tbody>
            {checks.map((c) => (
              <tr key={c.name}>
                <td style={{ width: 28 }} aria-label={c.ok ? "OK" : "Problem"}>{c.ok ? "✓" : "✗"}</td>
                <td><strong>{c.name}</strong><div className="small muted" style={{ overflowWrap: "anywhere" }}>{c.detail}</div></td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="small muted">Environment-variable changes on Vercel only take effect after a redeploy.</p>
        <p className="small"><a href="/">Public research view</a> · <a href="/desk">Research Desk</a></p>
      </div>
    </main>
  );
}
