"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import { useToast } from "@/components/toast";
import type { ActionResult } from "@/lib/types";

type Action = (prev: ActionResult, fd: FormData) => Promise<ActionResult>;

/** A form bound to a server action, with pending state and a result message. */
export function ActionForm({
  action,
  children,
  className,
  hidden,
}: {
  action: Action;
  children: React.ReactNode;
  className?: string;
  hidden?: Record<string, string>;
}) {
  const toast = useToast();
  // Report success through the layout toast: the form itself often unmounts once the
  // page refreshes (e.g. a reviewed item leaves the queue). Errors stay inline.
  const [state, formAction] = useActionState(async (prev: ActionResult, fd: FormData) => {
    const result = await action(prev, fd);
    if (result?.ok && result.message && toast) toast(result.message);
    return result;
  }, null);
  const showInline = state?.message && (!state.ok || !toast);
  return (
    <form action={formAction} className={className}>
      {hidden && Object.entries(hidden).map(([k, v]) => <input key={k} type="hidden" name={k} value={v} />)}
      {children}
      {showInline && state?.message && (
        <p role="status" className={state.ok ? "notice notice-ok" : "notice notice-error"}>
          {state.message}
        </p>
      )}
    </form>
  );
}

export function SubmitButton({
  children,
  variant = "primary",
  name,
  value,
}: {
  children: React.ReactNode;
  variant?: "primary" | "secondary" | "danger";
  name?: string;
  value?: string;
}) {
  const { pending } = useFormStatus();
  return (
    <button type="submit" className={`btn btn-${variant}`} disabled={pending} name={name} value={value} aria-busy={pending}>
      {children}
    </button>
  );
}
