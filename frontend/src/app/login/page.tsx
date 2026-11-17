import type { Metadata } from "next";

import { signIn } from "@/app/actions";
import { ActionForm, SubmitButton } from "@/components/forms";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
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
        <p className="dev-banner">
          Development sign-in: no password is checked. Replace with university single sign-on before real staff data is
          loaded.
        </p>
        <ActionForm action={signIn} className="stack">
          <label>
            Email address
            <input type="email" name="email" required autoComplete="email" placeholder="name@fuo.edu.ng" />
          </label>
          <div>
            <SubmitButton>Sign in</SubmitButton>
          </div>
        </ActionForm>
        <p className="small muted">
          Accounts are created by a Super Administrator with <code>furis create-user</code>.
        </p>
      </div>
    </main>
  );
}
