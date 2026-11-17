"use client";

export default function PortalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="card stack" role="alert">
      <h1>Something went wrong</h1>
      <p className="muted">{error.message || "The page could not be loaded."}</p>
      <div><button className="btn btn-secondary" onClick={reset}>Try again</button></div>
    </div>
  );
}
