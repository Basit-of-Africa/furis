import { NextResponse, type NextRequest } from "next/server";

// Unauthenticated visitors go to sign-in. The API still enforces every permission.
export function middleware(req: NextRequest) {
  if (!req.cookies.get("furis_user")) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.search = "";
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = { matcher: ["/((?!login|_next/|favicon.ico).*)"] };
