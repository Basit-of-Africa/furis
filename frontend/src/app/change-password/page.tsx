import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { signOut } from "@/app/actions";
import { ChangePasswordForm } from "@/components/change-password";
import { getMe } from "@/lib/api";

export const metadata: Metadata = { title: "Choose your password" };
export const dynamic = "force-dynamic";

/** First sign-in (or after a reset): the API allows nothing else until this is done. */
export default async function ChangePasswordPage() {
  const me = await getMe();
  if (!me.must_change_password) redirect("/desk");
  return (
    <main className="login-wrap">
      <div className="card login-card stack">
        <h1>Choose your password</h1>
        <p className="muted">
          Welcome, {me.full_name}. You signed in with a temporary password. Choose your own to continue.
        </p>
        <ChangePasswordForm submitLabel="Save and continue" continueTo="/desk" />
        <form action={signOut}>
          <button className="btn btn-secondary" type="submit">Sign out</button>
        </form>
      </div>
    </main>
  );
}
