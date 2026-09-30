export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/backend/v1${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  if (response.status === 401) {
    window.location.assign("/login");
    throw new Error("Authentication required");
  }

  const body = response.status === 204 ? null : await response.json();
  if (!response.ok) {
    const detail = body && typeof body === "object" && "detail" in body
      ? String(body.detail)
      : "Request failed";
    throw new Error(detail);
  }
  return body as T;
}
