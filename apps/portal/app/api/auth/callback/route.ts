import { NextRequest, NextResponse } from "next/server";

import { clearTokens, consumeLoginState, setTokens } from "../../../../lib/oidc";

export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get("code");
  const returnedState = request.nextUrl.searchParams.get("state");
  const error = request.nextUrl.searchParams.get("error");
  const tokenUrl = process.env.OIDC_TOKEN_URL;
  const clientId = process.env.OIDC_CLIENT_ID;
  const clientSecret = process.env.OIDC_CLIENT_SECRET;
  const redirectUri = process.env.OIDC_REDIRECT_URI;
  const portalUrl = process.env.PORTAL_PUBLIC_URL ?? request.nextUrl.origin;

  if (error) {
    await clearTokens();
    return NextResponse.redirect(new URL("/?auth=failed", portalUrl));
  }

  const { state, verifier } = await consumeLoginState();
  if (
    !code ||
    !returnedState ||
    !state ||
    !verifier ||
    returnedState !== state ||
    !tokenUrl ||
    !clientId ||
    !redirectUri
  ) {
    await clearTokens();
    return NextResponse.redirect(new URL("/?auth=invalid", portalUrl));
  }

  const body = new URLSearchParams({
    grant_type: "authorization_code",
    code,
    client_id: clientId,
    redirect_uri: redirectUri,
    code_verifier: verifier,
  });
  if (clientSecret) body.set("client_secret", clientSecret);

  const response = await fetch(tokenUrl, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body,
    cache: "no-store",
  });

  if (!response.ok) {
    await clearTokens();
    return NextResponse.redirect(new URL("/?auth=token_error", portalUrl));
  }

  const payload = await response.json();
  if (!payload.access_token) {
    await clearTokens();
    return NextResponse.redirect(new URL("/?auth=token_error", portalUrl));
  }

  await setTokens(payload);
  return NextResponse.redirect(new URL("/", portalUrl));
}
