import { NextRequest } from "next/server";

export function hasTrustedOrigin(request: NextRequest): boolean {
  if (request.headers.get("sec-fetch-site") === "cross-site") return false;
  const origin = request.headers.get("origin");
  if (origin === null) return true;
  // NextURL normalizes loopback IPs to localhost. Preserve the browser's Host.
  const host = request.headers.get("host");
  if (!host) return false;
  try {
    return origin === new URL(`${request.nextUrl.protocol}//${host}`).origin;
  } catch {
    return false;
  }
}
