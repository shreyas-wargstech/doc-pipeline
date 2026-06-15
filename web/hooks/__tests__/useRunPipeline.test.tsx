import { renderHook, act, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { useRunPipeline } from "@/hooks/useRunPipeline";

// Mock fetch globally (apiGet/apiPost use it).
const mockFetch = vi.fn();
global.fetch = mockFetch as unknown as typeof fetch;

// Minimal EventSource stub.
class MockEventSource {
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  readyState = 1;
  close = vi.fn();
  constructor(public url: string, public opts?: { withCredentials?: boolean }) {}
}
vi.stubGlobal("EventSource", MockEventSource);

function makeRunState(overrides: Record<string, unknown> = {}) {
  return {
    run_id: "run-1", folder: "/tmp", category: "practitioner", force: false,
    status: "running", total: 2, done: 0, skipped: 0, failed: 0, running: 0,
    items: [
      { filename: "a.pdf", status: "pending", document_id: null, stage: null, error: null },
      { filename: "b.pdf", status: "pending", document_id: null, stage: null, error: null },
    ],
    ...overrides,
  };
}

function jsonResponse(body: unknown) {
  return {
    ok: true,
    status: 200,
    headers: { get: () => "application/json" },
    json: async () => body,
  } as unknown as Response;
}

beforeEach(() => {
  mockFetch.mockReset();
  // Default: no active run on mount.
  mockFetch.mockResolvedValue(jsonResponse(null));
});

describe("useRunPipeline — on-mount recovery", () => {
  it("queries /api/pipelines/runs on mount; null → no run", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(null));
    const { result } = renderHook(() => useRunPipeline());
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/pipelines/runs"),
        expect.anything(),
      );
    });
    expect(result.current.run).toBeNull();
  });

  it("restores an active run on mount", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(makeRunState({ status: "running" })));
    const { result } = renderHook(() => useRunPipeline());
    await waitFor(() => expect(result.current.run).not.toBeNull());
    expect(result.current.run?.run_id).toBe("run-1");
    expect(result.current.isRunning).toBe(true);
  });

  it("restores a paused run on mount and exposes isPaused", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(makeRunState({ status: "paused" })));
    const { result } = renderHook(() => useRunPipeline());
    await waitFor(() => expect(result.current.run).not.toBeNull());
    expect(result.current.isPaused).toBe(true);
    expect(result.current.isRunning).toBe(false);
  });
});

describe("useRunPipeline — pause/resume", () => {
  it("pause() posts to the pause endpoint", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(makeRunState()));
    mockFetch.mockResolvedValueOnce(jsonResponse({ ok: true }));

    const { result } = renderHook(() => useRunPipeline());
    await waitFor(() => expect(result.current.run).not.toBeNull());
    await act(async () => { await result.current.pause(); });

    expect(mockFetch.mock.calls.some(([url]) => String(url).includes("/pause"))).toBe(true);
  });

  it("resume() posts to the resume endpoint", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(makeRunState({ status: "paused" })));
    mockFetch.mockResolvedValueOnce(jsonResponse({ run_id: "run-1", total: 2 }));

    const { result } = renderHook(() => useRunPipeline());
    await waitFor(() => expect(result.current.isPaused).toBe(true));
    await act(async () => { await result.current.resume(); });

    expect(mockFetch.mock.calls.some(([url]) => String(url).includes("/resume"))).toBe(true);
  });
});
