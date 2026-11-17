import { NextResponse, type NextRequest } from "next/server";

// Unauthenticated visitors go to sign-in. The API still enforces every permission.
export function middleware(req: NextRequest) {
  if (!req.cookies.get("furis_session")) {
    const url = req.nextUrl.clone();
    const next = req.nextUrl.pathname + req.nextUrl.search;
    url.pathname = "/login";
    url.search = next !== "/" ? `?next=${encodeURIComponent(next)}` : "";
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = { matcher: ["/((?!login|auth/|_next/|favicon.ico).*)"] };
