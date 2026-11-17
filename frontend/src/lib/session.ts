import "server-only";

import { cookies } from "next/headers";

export const SESSION_COOKIE = "furis_session";
export const OIDC_COOKIE = "furis_oidc";
export const AUTH_ERROR_COOKIE = "furis_auth_error";

export const API_BASE = (process.env.FURIS_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

/** Secure cookies whenever the portal is served over https, and always in production. */
export function secureCookies(): boolean {
  return process.env.NODE_ENV === "production" || (process.env.APP_URL ?? "").startsWith("https://");
}

export async function setSession(token: string, expiresAt: string) {
  const maxAge = Math.max(60, Math.floor((new Date(expiresAt).getTime() - Date.now()) / 1000));
  (await cookies()).set(SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: secureCookies(),
    path: "/",
    maxAge,
  });
}

export interface SessionResponse {
  token: string;
  expires_at: string;
}

export async function authMode(): Promise<"password" | "oidc" | "dev_header" | "unavailable"> {
  try {
    const res = await fetch(`${API_BASE}/auth/config`, { cache: "no-store" });
    if (!res.ok) return "unavailable";
    return ((await res.json()) as { mode: "password" | "oidc" | "dev_header" }).mode;
  } catch {
    return "unavailable";
  }
}
