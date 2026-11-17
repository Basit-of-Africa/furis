import Link from "next/link";

export default function PublicLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="public">
      <header className="public-header">
        <div className="public-inner">
          <Link href="/" className="brand" style={{ color: "inherit", textDecoration: "none" }}>
            <div className="brand-mark" aria-hidden>FU</div>
            <div>
              <div className="brand-name">Fountain University Research</div>
              <div className="brand-sub">Osogbo, Nigeria</div>
            </div>
          </Link>
          <nav className="public-nav" aria-label="Main">
            <Link href="/">Overview</Link>
            <Link href="/publications">Publications</Link>
            <Link href="/researchers">Researchers</Link>
          </nav>
        </div>
      </header>
      <main className="public-inner public-main">{children}</main>
      <footer className="public-inner public-footer">
        <p>
          Listed here are publications the Fountain University Research Desk has confirmed. Is something of yours
          missing or wrong? Contact the Research Desk.
        </p>
        <p><Link href="/desk">Research Desk sign-in</Link></p>
      </footer>
    </div>
  );
}
