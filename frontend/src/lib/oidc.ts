import "server-only";

import { createHash, randomBytes } from "node:crypto";

/**
 * OpenID Connect client for the portal (authorization-code flow with PKCE).
 * The portal is a confidential client: the client secret never reaches the browser.
 * The portal does not decide who the user is; it hands the ID token to the API,
 * which verifies it and issues the FURIS session (backend/furis/auth.py).
 */

export interface OidcConfig {
  issuer: string;
  clientId: string;
  clientSecret: string;
  redirectUri: string;
  postLogoutRedirectUri: string;
  scopes: string;
}

export function oidcConfig(): OidcConfig {
  const issuer = process.env.OIDC_ISSUER;
  const clientId = process.env.OIDC_CLIENT_ID;
  const clientSecret = process.env.OIDC_CLIENT_SECRET;
  const appUrl = process.env.APP_URL?.replace(/\/$/, "");
  if (!issuer || !clientId || !clientSecret || !appUrl) {
    throw new Error("Single sign-on needs OIDC_ISSUER, OIDC_CLIENT_ID, OIDC_CLIENT_SECRET and APP_URL.");
  }
  // The redirect URI comes from configuration, never from the request's Host header.
  return {
    issuer: issuer.replace(/\/$/, ""),
    clientId,
    clientSecret,
    redirectUri: `${appUrl}/auth/callback`,
    postLogoutRedirectUri: `${appUrl}/login`,
    scopes: process.env.OIDC_SCOPES ?? "openid email profile",
  };
}

interface Discovery {
  issuer: string;
  authorization_endpoint: string;
  token_endpoint: string;
  end_session_endpoint?: string;
}

let cached: { doc: Discovery; at: number } | null = null;

export async function discover(cfg: OidcConfig): Promise<Discovery> {
  if (cached && Date.now() - cached.at < 3_600_000) return cached.doc;
  const res = await fetch(`${cfg.issuer}/.well-known/openid-configuration`, { cache: "no-store" });
  if (!res.ok) throw new Error(`OIDC discovery failed (${res.status})`);
  const doc = (await res.json()) as Discovery;
  if (doc.issuer.replace(/\/$/, "") !== cfg.issuer) throw new Error("OIDC discovery issuer mismatch");
  cached = { doc, at: Date.now() };
  return doc;
}

const b64url = (buf: Buffer) => buf.toString("base64url");
export const randomToken = (bytes = 32) => b64url(randomBytes(bytes));
export const pkceChallenge = (verifier: string) => b64url(createHash("sha256").update(verifier).digest());

/** Only same-site relative paths are allowed as post-login destinations (no open redirect). */
export function safeNext(next: string | null | undefined): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return "/desk";
  return next;
}
