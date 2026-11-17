import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { cache } from "react";

import type { Me } from "./types";

export const SESSION_COOKIE = "furis_user";
const BASE = (process.env.FURIS_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

/**
 * DEV AUTH: the backend's `dev_header` mode trusts X-User-Email. The portal keeps
 * the signed-in email in an httpOnly cookie and forwards it server-side.
 * Replace with the university's SSO (and a real token) before production.
 */
async function authHeaders(): Promise<Record<string, string>> {
  const email = (await cookies()).get(SESSION_COOKIE)?.value;
  return email ? { "X-User-Email": email } : {};
}

function detail(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) return d.map((e) => (e as { msg?: string }).msg ?? "invalid input").join("; ");
  }
  return fallback;
}

async function request<T>(method: string, path: string, body?: BodyInit | object): Promise<T> {
  const headers: Record<string, string> = { ...(await authHeaders()) };
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { method, headers, body: payload, cache: "no-store" });
  } catch {
    throw new ApiError(503, `The FURIS API is not reachable at ${BASE}.`);
  }
  const text = await res.text();
  const json = text ? JSON.parse(text) : null;
  if (!res.ok) throw new ApiError(res.status, detail(json, `Request failed (${res.status})`));
  return json as T;
}

/** GET for server components. Sends the user to sign-in when the session is not valid. */
export async function apiGet<T>(path: string): Promise<T> {
  try {
    return await request<T>("GET", path);
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) redirect("/login");
    throw e;
  }
}

/** GET that returns null on 404/403 instead of throwing (for optional or scoped data). */
export async function apiGetOptional<T>(path: string): Promise<T | null> {
  try {
    return await apiGet<T>(path);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 403)) return null;
    throw e;
  }
}

export const apiSend = <T>(method: "POST" | "PATCH", path: string, body?: BodyInit | object) =>
  request<T>(method, path, body);

/** The signed-in user, fetched once per request. */
export const getMe = cache(async (): Promise<Me> => apiGet<Me>("/me"));

export function qs(params: Record<string, string | number | undefined | null>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}
