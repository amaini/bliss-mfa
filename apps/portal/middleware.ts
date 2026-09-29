import { NextRequest, NextResponse } from "next/server";

const PUBLIC_PREFIXES = [
  "/plans",
  "/onboarding",
  "/api/auth",
  "/_next",
  "/favicon.ico",
];

export function middleware(request: NextRequest) {
  const path = request.nextUrl.pathname;

  if (PUBLIC_PREFIXES.some((prefix) => path.startsWith(prefix))) {
    return NextResponse.next();
  }

  const access = request.cookies.get("bliss_access_token")?.value;
  const refresh = request.cookies.get("bliss_refresh_token")?.value;
  if (access || refresh) {
    return NextResponse.next();
  }

  const login = new URL("/api/auth/login", request.url);
  return NextResponse.redirect(login);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image).*)"],
};
