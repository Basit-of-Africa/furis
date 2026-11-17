import type { Metadata } from "next";
import { cookies } from "next/headers";

import { signIn } from "@/app/actions";
import { ActionForm, SubmitButton } from "@/components/forms";
import { safeNext } from "@/lib/oidc";
import { AUTH_ERROR_COOKIE, authMode } from "@/lib/session";

export const metadata: Metadata = { title: "Sign in" };
export const dynamic = "force-dynamic";

const QUERY_ERRORS: Record<string, string> = {
  unavailable: "The sign-in service is unavailable. Try again shortly.",
};

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ next?: string; error?: string }> }) {
  const sp = await searchParams;
  const next = safeNext(sp.next);
  const mode = await authMode();
  // Messages come only from our own callback (httpOnly cookie) or a fixed list; never from the URL text.
  const error = (await cookies()).get(AUTH_ERROR_COOKIE)?.value ?? (sp.error ? QUERY_ERRORS[sp.error] : undefined);

  return (
    <main className="login-wrap">
      <div className="card login-card stack">
        <div className="brand">
          <div className="brand-mark" aria-hidden>FU</div>
          <div>
            <div className="brand-name">FURIS</div>
            <div className="brand-sub">Research Intelligence System</div>
          </div>
        </div>

        {error && <p role="alert" className="notice notice-error" style={{ marginTop: 0 }}>{error}</p>}

        {mode === "oidc" && (
          <>
            <p className="muted">Sign in with your Fountain University account.</p>
            <div>
              <a className="btn btn-primary" href={`/auth/login${next !== "/" ? `?next=${encodeURIComponent(next)}` : ""}`}>
                Sign in with university account
              </a>
            </div>
            <p className="small muted">
              Signing in does not create a FURIS account. If you are told you have no account, ask the Research Office.
            </p>
          </>
        )}

        {mode === "dev_header" && (
          <>
            <p className="dev-banner">
              Development sign-in: no password is checked. Production requires single sign-on, and the API refuses to
              start without it.
            </p>
            <ActionForm action={signIn} className="stack" hidden={{ next }}>
              <label>
                Email address
                <input type="email" name="email" required autoComplete="email" placeholder="name@fuo.edu.ng" />
              </label>
              <div>
                <SubmitButton>Sign in</SubmitButton>
              </div>
            </ActionForm>
          </>
        )}

        {mode === "unavailable" && (
          <p className="notice notice-error" style={{ marginTop: 0 }}>The FURIS API is not reachable. Try again shortly.</p>
        )}
      </div>
    </main>
  );
}
