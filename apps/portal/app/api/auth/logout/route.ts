import { NextRequest, NextResponse } from "next/server";

import { clearTokens } from "../../../../lib/oidc";

export async function GET(request: NextRequest) {
  await clearTokens();
  const portalUrl = process.env.PORTAL_PUBLIC_URL ?? request.nextUrl.origin;
  const endSessionUrl = process.env.OIDC_END_SESSION_URL;

  if (!endSessionUrl) {
    return NextResponse.redirect(new URL("/", portalUrl));
  }

  const url = new URL(endSessionUrl);
  url.searchParams.set("post_logout_redirect_uri", portalUrl);
  return NextResponse.redirect(url);
}
