import { redirect } from "next/navigation";

import { createDeskUser, resetDeskPassword, setDeskUserActive } from "@/app/actions";
import { ActionForm, SubmitButton } from "@/components/forms";
import { apiGet, getMe } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/format";
import { authMode } from "@/lib/session";
import type { DeskUser } from "@/lib/types";

export const metadata = { title: "Research Desk team" };

export default async function TeamPage() {
  const me = await getMe();
  if (me.role !== "super_admin") redirect("/desk");
  const [users, mode] = await Promise.all([apiGet<DeskUser[]>("/users"), authMode()]);
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Research Desk team</h1>
          <p>
            People who can sign in to the Research Desk. Researchers don&apos;t need accounts: they use the public
            research view.
          </p>
        </div>
      </div>

      <section className="card" style={{ marginBottom: 16 }}>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.full_name}{u.id === me.id && <span className="muted"> (you)</span>}</td>
                  <td>{u.email}</td>
                  <td>{ROLE_LABEL[u.role]}</td>
                  <td>
                    {!u.is_active ? <span className="badge">Deactivated</span>
                      : u.locked ? <span className="badge badge-warn">Locked after failed sign-ins</span>
                      : u.must_change_password ? <span className="badge badge-info">Awaiting first sign-in</span>
                      : <span className="badge badge-good">Active</span>}
                  </td>
                  <td>
                    {u.id !== me.id && (
                      <div className="row">
                        {mode === "password" && u.is_active && (
                          <ActionForm action={resetDeskPassword} hidden={{ user_id: u.id }} keepMessage>
                            <SubmitButton variant="secondary">Reset password</SubmitButton>
                          </ActionForm>
                        )}
                        <ActionForm action={setDeskUserActive} hidden={{ user_id: u.id, is_active: String(!u.is_active) }}>
                          <SubmitButton variant={u.is_active ? "danger" : "secondary"}>
                            {u.is_active ? "Deactivate" : "Reactivate"}
                          </SubmitButton>
                        </ActionForm>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card" style={{ maxWidth: 640 }}>
        <h2>Add a team member</h2>
        <ActionForm action={createDeskUser} keepMessage>
          <div className="form-grid">
            <label>Full name<input type="text" name="full_name" required /></label>
            <label>Email<input type="email" name="email" required /></label>
            <label>
              Role
              <select name="role" defaultValue="research_office">
                <option value="research_office">{ROLE_LABEL.research_office}</option>
                <option value="super_admin">{ROLE_LABEL.super_admin} (can manage the team)</option>
              </select>
            </label>
          </div>
          <div className="form-actions"><SubmitButton>Add team member</SubmitButton></div>
        </ActionForm>
        {mode === "password" && (
          <p className="small muted" style={{ marginTop: 10 }}>
            FURIS shows a temporary password once. Pass it on privately; they choose their own at first sign-in.
          </p>
        )}
      </section>
    </>
  );
}
