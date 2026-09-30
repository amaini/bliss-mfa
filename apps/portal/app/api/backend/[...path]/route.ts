import { NextRequest, NextResponse } from "next/server";

import { getAccessToken, refreshAccessToken } from "../../../../lib/oidc";

type Context = {
  params: Promise<{ path: string[] }>;
};

function sameOrigin(request: NextRequest) {
  const origin = request.headers.get("origin");
  if (!origin) return true;
  return origin === request.nextUrl.origin;
}

async function forward(request: NextRequest, context: Context) {
  if (!sameOrigin(request) && request.method !== "GET") {
    return NextResponse.json({ error: "Invalid origin" }, { status: 403 });
  }

  const { path } = await context.params;
  const api = process.env.API_INTERNAL_URL;
  if (!api) {
    return NextResponse.json({ error: "API is not configured" }, { status: 503 });
  }

  let accessToken = await getAccessToken();
  if (!accessToken) {
    return NextResponse.json({ error: "Authentication required" }, { status: 401 });
  }

  const target = new URL(
    `${api.replace(/\/$/, "")}/${path.map(encodeURIComponent).join("/")}`
  );
  request.nextUrl.searchParams.forEach((value, key) => {
    target.searchParams.append(key, value);
  });

  const body =
    request.method === "GET" || request.method === "HEAD"
      ? undefined
      : await request.arrayBuffer();

  async function call(token: string) {
    return fetch(target, {
      method: request.method,
      headers: {
        authorization: `Bearer ${token}`,
        "content-type": request.headers.get("content-type") ?? "application/json",
      },
      body,
      cache: "no-store",
    });
  }

  let response = await call(accessToken);
  if (response.status === 401) {
    accessToken = await refreshAccessToken();
    if (accessToken) response = await call(accessToken);
  }

  const responseBody = await response.arrayBuffer();
  return new NextResponse(responseBody, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") ?? "application/json",
      "cache-control": "no-store",
    },
  });
}

export async function GET(request: NextRequest, context: Context) {
  return forward(request, context);
}

export async function POST(request: NextRequest, context: Context) {
  return forward(request, context);
}

export async function PATCH(request: NextRequest, context: Context) {
  return forward(request, context);
}

export async function DELETE(request: NextRequest, context: Context) {
  return forward(request, context);
}
