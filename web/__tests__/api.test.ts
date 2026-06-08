import { afterEach, describe, expect, it, vi } from "vitest";
import { apiGet, apiPost, ApiError } from "@/lib/api";

function mockFetch(status: number, body: unknown, contentType = "application/json") {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => contentType },
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response);
}

afterEach(() => vi.restoreAllMocks());

describe("api client", () => {
  it("apiGet returns parsed JSON on 200", async () => {
    vi.stubGlobal("fetch", mockFetch(200, { user: "alice" }));
    expect(await apiGet<{ user: string }>("/api/me")).toEqual({ user: "alice" });
  });

  it("apiGet throws ApiError with status on 401", async () => {
    vi.stubGlobal("fetch", mockFetch(401, { detail: "nope" }));
    await expect(apiGet("/api/me")).rejects.toMatchObject({ status: 401 } as Partial<ApiError>);
  });

  it("apiPost sends JSON body and returns parsed result", async () => {
    const f = mockFetch(200, { ok: true, message: "done" });
    vi.stubGlobal("fetch", f);
    const res = await apiPost("/api/documents/x/ingest", {});
    expect(res).toEqual({ ok: true, message: "done" });
    expect(f).toHaveBeenCalledWith("/api/documents/x/ingest", expect.objectContaining({ method: "POST" }));
  });
});
