import { NextResponse, type NextRequest } from "next/server";

import { discover, oidcConfig, pkceChallenge, randomToken, safeNext } from "@/lib/oidc";
import { OIDC_COOKIE, secureCookies } from "@/lib/session";

export const dynamic = "force-dynamic";

/** Starts university sign-in: state (CSRF), nonce (replay) and PKCE verifier are kept in a short-lived cookie. */
export async function GET(req: NextRequest) {
  const cfg = oidcConfig();
  let doc;
  try {
    doc = await discover(cfg);
  } catch {
    return NextResponse.redirect(new URL("/login?error=unavailable", cfg.redirectUri));
  }
  const state = randomToken();
  const nonce = randomToken();
  const verifier = randomToken(48);
  const next = safeNext(req.nextUrl.searchParams.get("next"));

  const url = new URL(doc.authorization_endpoint);
  url.search = new URLSearchParams({
    response_type: "code",
    client_id: cfg.clientId,
    redirect_uri: cfg.redirectUri,
    scope: cfg.scopes,
    state,
    nonce,
    code_challenge: pkceChallenge(verifier),
    code_challenge_method: "S256",
  }).toString();

  const res = NextResponse.redirect(url);
  res.cookies.set(OIDC_COOKIE, JSON.stringify({ state, nonce, verifier, next }), {
    httpOnly: true,
    sameSite: "lax", // sent on the provider's top-level redirect back to /auth/callback
    secure: secureCookies(),
    path: "/auth",
    maxAge: 600,
  });
  return res;
}
