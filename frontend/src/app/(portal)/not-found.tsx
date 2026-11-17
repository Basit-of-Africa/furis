import Link from "next/link";

export default function NotFound() {
  return (
    <div className="card stack">
      <h1>Not found</h1>
      <p className="muted">This record does not exist, or your role does not give you access to it.</p>
      <div><Link className="btn btn-secondary" href="/">Back to the portal</Link></div>
    </div>
  );
}
