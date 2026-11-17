import Link from "next/link";
import { redirect } from "next/navigation";

import { createDepartment, createFaculty, createResearcher, importStaff } from "@/app/actions";
import { ActionForm, SubmitButton } from "@/components/forms";
import { apiGet, getMe, qs } from "@/lib/api";
import { isAdmin, researcherName } from "@/lib/format";
import type { Department, Faculty, Researcher } from "@/lib/types";

export const metadata = { title: "Researchers" };

type Search = Promise<{ q?: string; faculty_id?: string }>;

export default async function ResearchersPage({ searchParams }: { searchParams: Search }) {
  const sp = await searchParams;
  const me = await getMe();
  if (me.role === "researcher") redirect(me.researcher_id ? `/desk/researchers/${me.researcher_id}` : "/desk/queue");
  const admin = isAdmin(me.role);
  const [researchers, faculties, departments] = await Promise.all([
    apiGet<Researcher[]>(`/researchers${qs({ q: sp.q, faculty_id: sp.faculty_id, limit: 500 })}`),
    apiGet<Faculty[]>("/faculties"),
    apiGet<Department[]>("/departments"),
  ]);
  const fac = new Map(faculties.map((f) => [f.id, f.name]));
  const dep = new Map(departments.map((d) => [d.id, d.name]));

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Researchers</h1>
          <p>The institutional researcher registry. Discovery searches each researcher&apos;s confirmed names and verified identifiers.</p>
        </div>
      </div>

      <form className="filters" method="get">
        <label style={{ minWidth: 240 }}>
          Search by name
          <input type="search" name="q" defaultValue={sp.q ?? ""} placeholder="Surname or first name" />
        </label>
        {me.role !== "faculty_admin" && (
          <label>
            Faculty
            <select name="faculty_id" defaultValue={sp.faculty_id ?? ""}>
              <option value="">All faculties</option>
              {faculties.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
            </select>
          </label>
        )}
        <button className="btn btn-secondary" type="submit">Search</button>
      </form>

      <section className="card" style={{ marginBottom: 16 }}>
        {researchers.length === 0 ? (
          <p className="empty">No researchers found{sp.q ? ` for “${sp.q}”` : ""}.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Name</th><th>Staff no.</th><th>Faculty</th><th>Department</th><th>Status</th></tr></thead>
              <tbody>
                {researchers.map((r) => (
                  <tr key={r.id}>
                    <td><Link href={`/desk/researchers/${r.id}`}>{researcherName(r)}</Link></td>
                    <td className="mono">{r.staff_number ?? "—"}</td>
                    <td>{r.faculty_id ? fac.get(r.faculty_id) ?? "—" : "—"}</td>
                    <td>{r.department_id ? dep.get(r.department_id) ?? "—" : "—"}</td>
                    <td>{r.employment_status.replace("_", " ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {admin && (
        <div className="grid-2">
          <section className="card">
            <h2>Add a researcher</h2>
            <ActionForm action={createResearcher}>
              <div className="form-grid">
                <label>First name<input type="text" name="first_name" required /></label>
                <label>Middle name(s)<input type="text" name="middle_name" /></label>
                <label>Surname<input type="text" name="last_name" required /></label>
                <label>Staff number<input type="text" name="staff_number" /></label>
                <label>Email<input type="email" name="email" /></label>
                <label>
                  Faculty
                  <select name="faculty_id" defaultValue="">
                    <option value="">—</option>
                    {faculties.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
                  </select>
                </label>
                <label>
                  Department
                  <select name="department_id" defaultValue="">
                    <option value="">—</option>
                    {departments.map((d) => <option key={d.id} value={d.id}>{fac.get(d.faculty_id)} · {d.name}</option>)}
                  </select>
                </label>
              </div>
              <div className="form-actions"><SubmitButton>Add researcher</SubmitButton></div>
            </ActionForm>
            <p className="small muted" style={{ marginTop: 10 }}>Add employment history and identifiers on the researcher&apos;s page.</p>
          </section>

          <div className="stack">
            <section className="card">
              <h2>Import staff from CSV</h2>
              <p className="small muted" style={{ marginBottom: 10 }}>
                Columns: staff_number, first_name, middle_name, last_name, email, faculty, department, employment_start,
                employment_end, employment_type, orcid. Re-importing updates by staff number. Imported ORCIDs stay
                unverified until checked.
              </p>
              <ActionForm action={importStaff}>
                <input type="file" name="file" accept=".csv,text/csv" required />
                <div className="form-actions"><SubmitButton>Import</SubmitButton></div>
              </ActionForm>
            </section>
            <section className="card">
              <h2>Faculties and departments</h2>
              <ActionForm action={createFaculty}>
                <div className="form-grid">
                  <label>New faculty<input type="text" name="name" required /></label>
                  <label>Code<input type="text" name="code" /></label>
                </div>
                <div className="form-actions"><SubmitButton variant="secondary">Add faculty</SubmitButton></div>
              </ActionForm>
              {faculties.length > 0 && (
                <ActionForm action={createDepartment}>
                  <div className="form-grid" style={{ marginTop: 14 }}>
                    <label>
                      Faculty
                      <select name="faculty_id" required defaultValue="">
                        <option value="" disabled>Choose…</option>
                        {faculties.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
                      </select>
                    </label>
                    <label>New department<input type="text" name="name" required /></label>
                  </div>
                  <div className="form-actions"><SubmitButton variant="secondary">Add department</SubmitButton></div>
                </ActionForm>
              )}
            </section>
          </div>
        </div>
      )}
    </>
  );
}
