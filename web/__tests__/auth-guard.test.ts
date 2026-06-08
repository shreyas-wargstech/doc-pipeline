import { describe, expect, it } from "vitest";
import { redirectTarget } from "@/lib/auth-guard";

describe("redirectTarget", () => {
  it("redirects unauthenticated user away from a protected path to /login", () => {
    expect(redirectTarget("/", false)).toBe("/login");
    expect(redirectTarget("/documents/abc", false)).toBe("/login");
  });
  it("lets an authenticated user through (null = no redirect)", () => {
    expect(redirectTarget("/", true)).toBeNull();
  });
  it("redirects an authenticated user away from /login to home", () => {
    expect(redirectTarget("/login", true)).toBe("/");
  });
  it("lets an unauthenticated user reach /login", () => {
    expect(redirectTarget("/login", false)).toBeNull();
  });
});
