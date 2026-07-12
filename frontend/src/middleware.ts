import { NextResponse, type NextRequest } from "next/server";

/**
 * Route guard. Reads the lightweight `smarttrip-session` cookie (set client-side
 * alongside the Zustand store on login/logout — see authStore's `persist`
 * config) purely as a presence check; the actual JWT stays out of the cookie
 * jar and is validated by the backend on every request.
 */
const PUBLIC_ROUTES = ["/login", "/signup", "/forgot-password"];
const PROTECTED_PREFIXES = ["/home", "/trip-planner", "/saved-trips", "/chat", "/profile"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasSession = request.cookies.has("smarttrip-session");

  const isProtected = PROTECTED_PREFIXES.some((prefix) => pathname.startsWith(prefix));
  const isPublicAuthRoute = PUBLIC_ROUTES.some((route) => pathname.startsWith(route));

  if (isProtected && !hasSession) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirectTo", pathname);
    return NextResponse.redirect(loginUrl);
  }

  if (isPublicAuthRoute && hasSession) {
    return NextResponse.redirect(new URL("/home", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
