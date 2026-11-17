"use server";

import { cookies } from "next/headers";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { ApiError, apiSend } from "@/lib/api";
import { discover, oidcConfig, safeNext } from "@/lib/oidc";
import { API_BASE, SESSION_COOKIE, authMode, setSession, type SessionResponse } from "@/lib/session";
import type { ActionResult } from "@/lib/types";
const str = (fd: FormData, k: string) => {
  const v = fd.get(k);
  return typeof v === "string" && v.trim() !== "" ? v.trim() : undefined;
};

/** Run a mutation, refresh every page, and turn API errors into a message for the form. */
async function run(fn: () => Promise<unknown>, success: string): Promise<ActionResult> {
  try {
    await fn();
  } catch (e) {
    if (e instanceof ApiError) {
      if (e.status === 401) redirect("/login");
      return { ok: false, message: e.message };
    }
    throw e;
  }
  revalidatePath("/", "layout");
  return { ok: true, message: success };
}

// -- session ------------------------------------------------------------------

/** Development sign-in (API in dev_header mode only): exchanges an email for a session token. */
export async function signIn(_: ActionResult, fd: FormData): Promise<ActionResult> {
  const email = str(fd, "email")?.toLowerCase();
  if (!email) return { ok: false, message: "Enter your email address." };
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/auth/dev/session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
      cache: "no-store",
    });
  } catch {
    return { ok: false, message: `The FURIS API is not reachable at ${API_BASE}.` };
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) return { ok: false, message: typeof body?.detail === "string" ? body.detail : "Sign-in failed." };
  const session = body as SessionResponse;
  await setSession(session.token, session.expires_at);
  redirect(safeNext(str(fd, "next")));
}

/** Research Desk password sign-in (API in password mode). */
export async function signInPassword(_: ActionResult, fd: FormData): Promise<ActionResult> {
  const email = str(fd, "email")?.toLowerCase();
  const password = fd.get("password");
  if (!email || typeof password !== "string" || !password) return { ok: false, message: "Enter your email and password." };
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/auth/password/session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
      cache: "no-store",
    });
  } catch {
    return { ok: false, message: "The FURIS API is not reachable. Try again shortly." };
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) return { ok: false, message: typeof body?.detail === "string" ? body.detail : "Sign-in failed." };
  const session = body as SessionResponse & { user: { must_change_password: boolean } };
  await setSession(session.token, session.expires_at);
  redirect(session.user.must_change_password ? "/change-password" : safeNext(str(fd, "next")));
}

/** Change your own password. The API returns a new session; older sessions stop working. */
export async function changePassword(_: ActionResult, fd: FormData): Promise<ActionResult> {
  const current = fd.get("current_password");
  const next = fd.get("new_password");
  const confirm = fd.get("confirm_password");
  if (typeof current !== "string" || typeof next !== "string" || !current || !next) {
    return { ok: false, message: "Fill in every field." };
  }
  if (next !== confirm) return { ok: false, message: "The new passwords don't match." };
  let session: SessionResponse | undefined;
  const r = await run(async () => {
    session = await apiSend<SessionResponse>("POST", "/auth/password/change", {
      current_password: current,
      new_password: next,
    });
  }, "Password changed.");
  if (r?.ok && session) {
    await setSession(session.token, session.expires_at);
    if (str(fd, "continue_to")) redirect(safeNext(str(fd, "continue_to")));
  }
  return r;
}

type TempPassword = { user: { email: string }; temporary_password: string | null };

function tempMessage(t: TempPassword | undefined, what: string): ActionResult {
  if (!t) return { ok: false, message: "Something went wrong." };
  return {
    ok: true,
    message: t.temporary_password
      ? `${what} Temporary password for ${t.user.email}: ${t.temporary_password}. It is shown only once; pass it on privately. They must choose their own password at first sign-in.`
      : `${what} They sign in with the university account.`,
  };
}

export async function createDeskUser(_: ActionResult, fd: FormData): Promise<ActionResult> {
  let t: TempPassword | undefined;
  const r = await run(async () => {
    t = await apiSend<TempPassword>("POST", "/users", {
      email: str(fd, "email"),
      full_name: str(fd, "full_name"),
      role: str(fd, "role") ?? "research_office",
    });
  }, "");
  return r?.ok ? tempMessage(t, "Account created.") : r;
}

export async function resetDeskPassword(_: ActionResult, fd: FormData): Promise<ActionResult> {
  let t: TempPassword | undefined;
  const r = await run(async () => {
    t = await apiSend<TempPassword>("POST", `/users/${str(fd, "user_id")}/reset-password`);
  }, "");
  return r?.ok ? tempMessage(t, "Password reset; their current sessions have ended.") : r;
}

export async function setDeskUserActive(_: ActionResult, fd: FormData): Promise<ActionResult> {
  const active = str(fd, "is_active") === "true";
  return run(
    () => apiSend("PATCH", `/users/${str(fd, "user_id")}`, { is_active: active }),
    active ? "Account reactivated." : "Account deactivated.",
  );
}

/** Ends the FURIS session, then the provider session where it supports RP-initiated logout. */
export async function signOut() {
  (await cookies()).delete(SESSION_COOKIE);
  let providerLogout: string | null = null;
  if ((await authMode()) === "oidc") {
    try {
      const cfg = oidcConfig();
      const doc = await discover(cfg);
      if (doc.end_session_endpoint) {
        const url = new URL(doc.end_session_endpoint);
        url.searchParams.set("client_id", cfg.clientId);
        url.searchParams.set("post_logout_redirect_uri", cfg.postLogoutRedirectUri);
        providerLogout = url.toString();
      }
    } catch {
      // Provider unreachable: the FURIS session is already gone.
    }
  }
  redirect(providerLogout ?? "/login");
}

// -- verification -------------------------------------------------------------

export async function decideAuthorship(_: ActionResult, fd: FormData): Promise<ActionResult> {
  const decision = str(fd, "decision");
  return run(
    () =>
      apiSend("POST", "/verification/authorship", {
        publication_id: str(fd, "publication_id"),
        researcher_id: str(fd, "researcher_id"),
        decision,
        evidence: str(fd, "evidence"),
        comments: str(fd, "comments"),
      }),
    decision === "confirmed" ? "Authorship confirmed." : "Marked as not this researcher.",
  );
}

export async function decideAttribution(_: ActionResult, fd: FormData): Promise<ActionResult> {
  return run(
    () =>
      apiSend("POST", "/verification/attribution", {
        publication_id: str(fd, "publication_id"),
        researcher_id: str(fd, "researcher_id"),
        status: str(fd, "status"),
        evidence: str(fd, "evidence"),
        comments: str(fd, "comments"),
      }),
    "Attribution decision recorded.",
  );
}

export async function decideDuplicate(_: ActionResult, fd: FormData): Promise<ActionResult> {
  const status = str(fd, "status");
  return run(
    () => apiSend("POST", `/duplicates/${str(fd, "duplicate_id")}`, { status }),
    status === "merged" ? "Records merged." : "Kept as separate publications.",
  );
}

// -- registry -----------------------------------------------------------------

export async function createResearcher(_: ActionResult, fd: FormData): Promise<ActionResult> {
  return run(
    () =>
      apiSend("POST", "/researchers", {
        staff_number: str(fd, "staff_number"),
        first_name: str(fd, "first_name"),
        middle_name: str(fd, "middle_name"),
        last_name: str(fd, "last_name"),
        email: str(fd, "email"),
        faculty_id: str(fd, "faculty_id"),
        department_id: str(fd, "department_id"),
      }),
    "Researcher added. Name variants were generated.",
  );
}

export async function importStaff(_: ActionResult, fd: FormData): Promise<ActionResult> {
  const file = fd.get("file");
  if (!(file instanceof File) || file.size === 0) return { ok: false, message: "Choose a CSV file." };
  const body = new FormData();
  body.set("file", file, file.name);
  let result: { created: number; updated: number; errors: string[] } | undefined;
  const r = await run(async () => {
    result = await apiSend("POST", "/researchers/import", body);
  }, "");
  if (!r?.ok || !result) return r;
  const errs = result.errors.length ? ` ${result.errors.length} row(s) skipped: ${result.errors.slice(0, 3).join("; ")}` : "";
  return { ok: result.errors.length === 0, message: `${result.created} created, ${result.updated} updated.${errs}` };
}

export async function createFaculty(_: ActionResult, fd: FormData): Promise<ActionResult> {
  return run(() => apiSend("POST", "/faculties", { name: str(fd, "name"), code: str(fd, "code") }), "Faculty added.");
}

export async function createDepartment(_: ActionResult, fd: FormData): Promise<ActionResult> {
  return run(
    () => apiSend("POST", "/departments", { faculty_id: str(fd, "faculty_id"), name: str(fd, "name"), code: str(fd, "code") }),
    "Department added.",
  );
}

export async function addIdentifier(_: ActionResult, fd: FormData): Promise<ActionResult> {
  return run(
    () =>
      apiSend("POST", `/researchers/${str(fd, "researcher_id")}/identifiers`, {
        identifier_type: str(fd, "identifier_type"),
        identifier_value: str(fd, "identifier_value"),
        verified: fd.get("verified") === "on",
      }),
    "Identifier added.",
  );
}

export async function verifyIdentifier(_: ActionResult, fd: FormData): Promise<ActionResult> {
  return run(() => apiSend("POST", `/identifiers/${str(fd, "identifier_id")}/verify`), "Identifier verified.");
}

export async function addAlias(_: ActionResult, fd: FormData): Promise<ActionResult> {
  return run(
    () => apiSend("POST", `/researchers/${str(fd, "researcher_id")}/variants`, { variant_name: str(fd, "variant_name") }),
    "Name added as a confirmed alias.",
  );
}

export async function reviewVariant(_: ActionResult, fd: FormData): Promise<ActionResult> {
  const status = str(fd, "confirmation_status");
  return run(
    () => apiSend("PATCH", `/variants/${str(fd, "variant_id")}`, { confirmation_status: status }),
    status === "confirmed" ? "Name confirmed; it will be searched next run." : "Name rejected.",
  );
}

export async function addEmployment(_: ActionResult, fd: FormData): Promise<ActionResult> {
  return run(
    () =>
      apiSend("POST", `/researchers/${str(fd, "researcher_id")}/employment`, {
        institution_name: str(fd, "institution_name"),
        is_fountain_university: fd.get("is_fountain_university") === "on",
        start_date: str(fd, "start_date"),
        end_date: str(fd, "end_date"),
        employment_type: str(fd, "employment_type"),
        evidence_reference: str(fd, "evidence_reference"),
      }),
    "Employment period added.",
  );
}

export async function startDiscovery(_: ActionResult, fd: FormData): Promise<ActionResult> {
  // The API says whether it started the run or queued it for the scheduled worker.
  let message = "Discovery requested.";
  const r = await run(async () => {
    const res = await apiSend<{ message?: string }>("POST", `/discovery/researchers/${str(fd, "researcher_id")}`);
    if (res?.message) message = res.message;
  }, "");
  return r?.ok ? { ok: true, message } : r;
}
