import { ChangePasswordForm } from "@/components/change-password";
import { getMe } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/format";
import { authMode } from "@/lib/session";

export const metadata = { title: "Your account" };

export default async function AccountPage() {
  const [me, mode] = await Promise.all([getMe(), authMode()]);
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Your account</h1>
          <p>{me.full_name} · {me.email} · {ROLE_LABEL[me.role]}</p>
        </div>
      </div>
      <section className="card" style={{ maxWidth: 480 }}>
        <h2>Password</h2>
        {mode === "password" ? (
          <>
            <p className="small muted" style={{ marginBottom: 12 }}>
              Changing your password signs you out everywhere else.
            </p>
            <ChangePasswordForm />
          </>
        ) : (
          <p className="muted small">You sign in with your university account, so there is no FURIS password to change.</p>
        )}
      </section>
    </>
  );
}
