import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { useCollapsible } from "@/hooks/useCollapsible";

describe("useCollapsible", () => {
  beforeEach(() => window.localStorage.clear());

  it("uses the provided default when nothing is stored", () => {
    const { result } = renderHook(() => useCollapsible("k1", true));
    expect(result.current.collapsed).toBe(true);
  });

  it("toggles and persists to localStorage", () => {
    const { result } = renderHook(() => useCollapsible("k2", false));
    act(() => result.current.toggle());
    expect(result.current.collapsed).toBe(true);
    expect(window.localStorage.getItem("collapse:k2")).toBe("true");
  });

  it("reads a previously stored value on mount", () => {
    window.localStorage.setItem("collapse:k3", "true");
    const { result } = renderHook(() => useCollapsible("k3", false));
    expect(result.current.collapsed).toBe(true);
  });
});
