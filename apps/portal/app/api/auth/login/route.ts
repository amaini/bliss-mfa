import { NextResponse } from "next/server";

import { codeChallenge, randomToken, setLoginState } from "../../../../lib/oidc";

export async function GET() {
  const authorizationUrl = process.env.OIDC_AUTHORIZATION_URL;
  const clientId = process.env.OIDC_CLIENT_ID;
  const redirectUri = process.env.OIDC_REDIRECT_URI;

  if (!authorizationUrl || !clientId || !redirectUri) {
    return NextResponse.json(
      { error: "OIDC is not configured" },
      { status: 503 }
    );
  }

  const state = randomToken();
  const verifier = randomToken(48);
  await setLoginState(state, verifier);

  const url = new URL(authorizationUrl);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("client_id", clientId);
  url.searchParams.set("redirect_uri", redirectUri);
  url.searchParams.set("scope", "openid profile email groups");
  url.searchParams.set("state", state);
  url.searchParams.set("code_challenge", codeChallenge(verifier));
  url.searchParams.set("code_challenge_method", "S256");

  return NextResponse.redirect(url);
}
