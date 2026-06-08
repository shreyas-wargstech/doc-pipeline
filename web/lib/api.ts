export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; this.name = "ApiError"; }
}

// Browser-only safety net. Server components / edge routes have no window and instead receive the thrown ApiError; the Next middleware handles their redirects.
function handle401(status: number) {
  if (status === 401 && typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    window.location.assign("/login");
  }
}

async function parse<T>(res: Response): Promise<T> {
  const ct = res.headers.get("content-type") || "";
  const body = ct.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    handle401(res.status);
    const msg = typeof body === "object" && body && "detail" in body ? String((body as { detail: unknown }).detail) : String(body);
    throw new ApiError(res.status, msg || `HTTP ${res.status}`);
  }
  return body as T;
}

export async function apiGet<T>(path: string): Promise<T> {
  return parse<T>(await fetch(path, { credentials: "same-origin" }));
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return parse<T>(
    await fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers: { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  );
}

export function imageUrl(documentId: string, pageNum: number): string {
  return `/api/documents/${documentId}/pages/${pageNum}/image`;
}
