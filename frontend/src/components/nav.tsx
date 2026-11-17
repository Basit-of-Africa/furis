"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export interface NavItem { href: string; label: string; count?: string }

export function Nav({ items }: { items: NavItem[] }) {
  const path = usePathname();
  return (
    <nav className="nav" aria-label="Main">
      {items.map((i) => {
        const active = i.href === "/desk" ? path === "/desk" : path === i.href || path.startsWith(`${i.href}/`);
        return (
          <Link key={i.href} href={i.href} aria-current={active ? "page" : undefined}>
            <span>{i.label}</span>
            {i.count && <span className="nav-count" aria-label={`${i.count} items`}>{i.count}</span>}
          </Link>
        );
      })}
    </nav>
  );
}
