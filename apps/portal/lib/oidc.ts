import crypto from "crypto";
import { cookies } from "next/headers";

const ACCESS_COOKIE = "bliss_access_token";
const REFRESH_COOKIE = "bliss_refresh_token";
const STATE_COOKIE = "bliss_oidc_state";
const VERIFIER_COOKIE = "bliss_oidc_verifier";

function secureCookie() {
  return process.env.NODE_ENV === "production";
}

export function base64url(input: Buffer) {
  return input
    .toString("base64")
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
}

export function randomToken(bytes = 32) {
  return base64url(crypto.randomBytes(bytes));
}

export function codeChallenge(verifier: string) {
  return base64url(crypto.createHash("sha256").update(verifier).digest());
}

export async function setLoginState(state: string, verifier: string) {
  const store = await cookies();
  const common = {
    httpOnly: true,
    secure: secureCookie(),
    sameSite: "lax" as const,
    path: "/",
    maxAge: 600,
  };

  store.set(STATE_COOKIE, state, common);
  store.set(VERIFIER_COOKIE, verifier, common);
}

export async function consumeLoginState() {
  const store = await cookies();
  const state = store.get(STATE_COOKIE)?.value ?? null;
  const verifier = store.get(VERIFIER_COOKIE)?.value ?? null;
  store.delete(STATE_COOKIE);
  store.delete(VERIFIER_COOKIE);
  return { state, verifier };
}

export async function setTokens(payload: {
  access_token: string;
  refresh_token?: string;
  expires_in?: number;
}) {
  const store = await cookies();
  store.set(ACCESS_COOKIE, payload.access_token, {
    httpOnly: true,
    secure: secureCookie(),
    sameSite: "lax",
    path: "/",
    maxAge: Math.max(60, payload.expires_in ?? 300),
  });

  if (payload.refresh_token) {
    store.set(REFRESH_COOKIE, payload.refresh_token, {
      httpOnly: true,
      secure: secureCookie(),
      sameSite: "lax",
      path: "/",
      maxAge: 60 * 60 * 24 * 30,
    });
  }
}

export async function getAccessToken() {
  const store = await cookies();
  return store.get(ACCESS_COOKIE)?.value ?? null;
}

export async function getRefreshToken() {
  const store = await cookies();
  return store.get(REFRESH_COOKIE)?.value ?? null;
}

export async function clearTokens() {
  const store = await cookies();
  store.delete(ACCESS_COOKIE);
  store.delete(REFRESH_COOKIE);
}

export async function refreshAccessToken() {
  const refreshToken = await getRefreshToken();
  const tokenUrl = process.env.OIDC_TOKEN_URL;
  const clientId = process.env.OIDC_CLIENT_ID;
  const clientSecret = process.env.OIDC_CLIENT_SECRET;

  if (!refreshToken || !tokenUrl || !clientId) return null;

  const body = new URLSearchParams({
    grant_type: "refresh_token",
    refresh_token: refreshToken,
    client_id: clientId,
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
    return null;
  }

  const payload = await response.json();
  if (!payload.access_token) return null;

  await setTokens(payload);
  return payload.access_token as string;
}
