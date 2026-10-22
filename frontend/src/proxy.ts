import { NextResponse, type NextRequest } from "next/server";

import { loginPath } from "@/lib/navigation";
import { protectionFor } from "@/lib/route-protection";

/**
 * Sends visitors without a session cookie to the login page before a protected page
 * renders. This is only a shortcut: the cookie may be expired or revoked, so the
 * pages still ask the API (/me) and treat a 401 as logged out.
 */
export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const protection = protectionFor(pathname);
  if (protection === null || request.cookies.has(protection.cookie)) {
    return NextResponse.next();
  }
  const target = new URL(loginPath(protection.area, `${pathname}${search}`), request.url);
  return NextResponse.redirect(target);
}

export const config = {
  matcher: ["/konto/:path*", "/admin/:path*"],
};
