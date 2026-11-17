import { timingSafeEqual } from "node:crypto";

import { NextResponse, type NextRequest } from "next/server";

import { discover, oidcConfig, safeNext } from "@/lib/oidc";
import { API_BASE, AUTH_ERROR_COOKIE, OIDC_COOKIE, SESSION_COOKIE, secureCookies, type SessionResponse } from "@/lib/session";

export const dynamic = "force-dynamic";

const same = (a: string, b: string) => a.length === b.length && timingSafeEqual(Buffer.from(a), Buffer.from(b));

export async function GET(req: NextRequest) {
  const cfg = oidcConfig();
  const fail = (message: string) => {
    const res = NextResponse.redirect(new URL("/login", cfg.redirectUri));
    res.cookies.delete({ name: OIDC_COOKIE, path: "/auth" });
    res.cookies.set(AUTH_ERROR_COOKIE, message.slice(0, 300), {
      httpOnly: true, sameSite: "lax", secure: secureCookies(), path: "/login", maxAge: 60,
    });
    return res;
  };

  const p = req.nextUrl.searchParams;
  if (p.get("error")) {
    return fail(p.get("error") === "access_denied" ? "Sign-in was cancelled." : "The sign-in provider reported an error.");
  }
  let saved: { state: string; nonce: string; verifier: string; next: string };
  try {
    saved = JSON.parse(req.cookies.get(OIDC_COOKIE)?.value ?? "");
  } catch {
    return fail("Your sign-in attempt expired. Please try again.");
  }
  const code = p.get("code");
  const state = p.get("state");
  if (!code || !state || !saved?.state || !same(state, saved.state)) {
    return fail("Sign-in could not be verified. Please try again.");
  }

  // Exchange the code (client_secret_post + PKCE verifier).
  let idToken: string | undefined;
  try {
    const doc = await discover(cfg);
    const tokenRes = await fetch(doc.token_endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded", Accept: "application/json" },
      body: new URLSearchParams({
        grant_type: "authorization_code",
        code,
        redirect_uri: cfg.redirectUri,
        client_id: cfg.clientId,
        client_secret: cfg.clientSecret,
        code_verifier: saved.verifier,
      }),
      cache: "no-store",
    });
    if (!tokenRes.ok) return fail("The sign-in provider rejected the request. Please try again.");
    idToken = ((await tokenRes.json()) as { id_token?: string }).id_token;
  } catch {
    return fail("The sign-in service is unavailable. Try again shortly.");
  }
  if (!idToken) return fail("The sign-in provider did not return an identity token.");

  // The API verifies the ID token and decides whether this person has a FURIS account.
  let session: SessionResponse;
  try {
    const res = await fetch(`${API_BASE}/auth/oidc/session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: idToken, nonce: saved.nonce }),
      cache: "no-store",
    });
    const body = await res.json().catch(() => null);
    if (!res.ok) return fail(typeof body?.detail === "string" ? body.detail : "Sign-in failed.");
    session = body as SessionResponse;
  } catch {
    return fail("The FURIS API is not reachable.");
  }

  const res = NextResponse.redirect(new URL(safeNext(saved.next), cfg.redirectUri));
  res.cookies.delete({ name: OIDC_COOKIE, path: "/auth" });
  const maxAge = Math.max(60, Math.floor((new Date(session.expires_at).getTime() - Date.now()) / 1000));
  res.cookies.set(SESSION_COOKIE, session.token, {
    httpOnly: true, sameSite: "lax", secure: secureCookies(), path: "/", maxAge,
  });
  return res;
}
