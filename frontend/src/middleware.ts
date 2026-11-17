import { NextResponse, type NextRequest } from "next/server";

// The Research Desk (/desk) needs a session; the public view does not.
// The API still enforces every permission.
export function middleware(req: NextRequest) {
  if (!req.cookies.get("furis_session")) {
    const url = req.nextUrl.clone();
    const next = req.nextUrl.pathname + req.nextUrl.search;
    url.pathname = "/login";
    url.search = next !== "/desk" ? `?next=${encodeURIComponent(next)}` : "";
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = { matcher: ["/desk", "/desk/:path*", "/change-password"] };
