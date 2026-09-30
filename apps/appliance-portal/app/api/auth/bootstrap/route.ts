import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  const api = process.env.APPLIANCE_API_URL;
  if (!api) return NextResponse.json({ detail: "API not configured" }, { status: 503 });

  const payload = await request.json();
  const response = await fetch(`${api.replace(/\/$/, "")}/v1/auth/bootstrap`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
  });

  const body = await response.json();
  if (!response.ok) return NextResponse.json(body, { status: response.status });

  const result = NextResponse.json({ ok: true });
  result.cookies.set("bliss_appliance_session", body.access_token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/",
    maxAge: 60 * 60 * 8,
  });
  return result;
}
