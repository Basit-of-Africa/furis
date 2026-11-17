import Link from "next/link";
import { redirect } from "next/navigation";

import { signOut } from "@/app/actions";
import { Nav, type NavItem } from "@/components/nav";
import { Toaster } from "@/components/toast";
import { apiGetOptional, getMe } from "@/lib/api";
import { ROLE_LABEL, isAdmin } from "@/lib/format";
import type { Duplicate, QueueItem } from "@/lib/types";

export const dynamic = "force-dynamic";

const count = (n: number | undefined, cap: number) => (n === undefined || n === 0 ? undefined : n >= cap ? `${cap}+` : String(n));

export default async function PortalLayout({ children }: { children: React.ReactNode }) {
  const me = await getMe();
  // A redirect (not an inline form) stops the desk pages, which render in parallel
  // with this layout and which the API refuses until the password is replaced.
  if (me.must_change_password) redirect("/change-password");
  const admin = isAdmin(me.role);
  const [queue, dups] = await Promise.all([
    apiGetOptional<QueueItem[]>("/verification/queue?limit=200"),
    admin ? apiGetOptional<Duplicate[]>("/duplicates") : Promise.resolve(null),
  ]);

  const items: NavItem[] = [
    ...(me.role === "researcher" ? [] : [{ href: "/desk", label: "Dashboard" }]),
    { href: "/desk/queue", label: me.role === "researcher" ? "My review queue" : "Review queue", count: count(queue?.length, 200) },
    { href: "/desk/publications", label: "Publications" },
    me.role === "researcher" && me.researcher_id
      ? { href: `/desk/researchers/${me.researcher_id}`, label: "My profile" }
      : { href: "/desk/researchers", label: "Researchers" },
    ...(admin ? [{ href: "/desk/duplicates", label: "Duplicates", count: count(dups?.length, 200) }] : []),
    ...(me.role === "super_admin" ? [{ href: "/desk/team", label: "Team" }] : []),
  ];

  return (
    <Toaster>
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark" aria-hidden>FU</div>
          <div>
            <div className="brand-name">FURIS</div>
            <div className="brand-sub">Research Desk</div>
          </div>
        </div>
        <Nav items={items} />
        <div className="user-box">
          <div>
            <div className="name"><Link href="/desk/account">{me.full_name}</Link></div>
            <div className="role">{ROLE_LABEL[me.role]}</div>
            <div className="small"><Link href="/" target="_blank">Public research view ↗</Link></div>
          </div>
          <form action={signOut}>
            <button className="btn btn-secondary" type="submit">Sign out</button>
          </form>
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
    </Toaster>
  );
}
