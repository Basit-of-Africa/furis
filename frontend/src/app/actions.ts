"use server";

import { cookies } from "next/headers";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { ApiError, SESSION_COOKIE, apiSend } from "@/lib/api";
import type { ActionResult } from "@/lib/types";

const BASE = (process.env.FURIS_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
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

// -- session (development sign-in) -------------------------------------------

export async function signIn(_: ActionResult, fd: FormData): Promise<ActionResult> {
  const email = str(fd, "email")?.toLowerCase();
  if (!email) return { ok: false, message: "Enter your email address." };
  let res: Response;
  try {
    res = await fetch(`${BASE}/me`, { headers: { "X-User-Email": email }, cache: "no-store" });
  } catch {
    return { ok: false, message: `The FURIS API is not reachable at ${BASE}.` };
  }
  if (!res.ok) return { ok: false, message: "No active FURIS account uses that email address." };
  (await cookies()).set(SESSION_COOKIE, email, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 12,
  });
  redirect("/");
}

export async function signOut() {
  (await cookies()).delete(SESSION_COOKIE);
  redirect("/login");
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
  return run(
    () => apiSend("POST", `/discovery/researchers/${str(fd, "researcher_id")}`),
    "Discovery started. Search runs appear below as each query finishes; refresh to update.",
  );
}
