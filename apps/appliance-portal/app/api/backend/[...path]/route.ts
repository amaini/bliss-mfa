import { NextRequest, NextResponse } from "next/server";

type Context = { params: Promise<{ path: string[] }> };

function sameOrigin(request: NextRequest) {
  const origin = request.headers.get("origin");
  return !origin || origin === request.nextUrl.origin;
}

async function forward(request: NextRequest, context: Context) {
  if (!sameOrigin(request) && request.method !== "GET") {
    return NextResponse.json({ detail: "Invalid origin" }, { status: 403 });
  }

  const api = process.env.APPLIANCE_API_URL;
  if (!api) return NextResponse.json({ detail: "API not configured" }, { status: 503 });

  const token = request.cookies.get("bliss_appliance_session")?.value;
  if (!token) return NextResponse.json({ detail: "Authentication required" }, { status: 401 });

  const { path } = await context.params;
  const target = new URL(
    `${api.replace(/\/$/, "")}/${path.map(encodeURIComponent).join("/")}`
  );
  request.nextUrl.searchParams.forEach((value, key) => target.searchParams.append(key, value));

  const body = ["GET", "HEAD"].includes(request.method) ? undefined : await request.arrayBuffer();
  const response = await fetch(target, {
    method: request.method,
    headers: {
      authorization: `Bearer ${token}`,
      "content-type": request.headers.get("content-type") ?? "application/json",
    },
    body,
    cache: "no-store",
  });

  return new NextResponse(await response.arrayBuffer(), {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") ?? "application/json",
      "cache-control": "no-store",
    },
  });
}

export async function GET(request: NextRequest, context: Context) { return forward(request, context); }
export async function POST(request: NextRequest, context: Context) { return forward(request, context); }
export async function DELETE(request: NextRequest, context: Context) { return forward(request, context); }
