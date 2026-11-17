"use client";

export default function PublicError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="card stack" role="alert">
      <h1>Research data is unavailable right now</h1>
      <p className="muted">
        The research data service could not be reached. Please try again in a moment. If this continues, contact the
        Fountain University Research Desk.
      </p>
      <div className="row">
        <button className="btn btn-primary" onClick={reset}>Try again</button>
        <a className="btn btn-secondary" href="/status">Technical status</a>
      </div>
    </div>
  );
}
