"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { LoginBrandPanel } from "@/components/auth/LoginBrandPanel";
import { useLogin } from "@/hooks/useAuth";
import { ApiError } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const login = useLogin();
  const [username, setU] = useState("");
  const [password, setP] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (login.isPending) return;
    setError(null);
    try {
      await login.mutateAsync({ username, password });
      router.replace("/");
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "Invalid username or password."
          : "Sign-in failed. Check your connection or try again.",
      );
    }
  };

  return (
    <main className="grid min-h-dvh md:grid-cols-2">
      <LoginBrandPanel />

      <div className="flex flex-col justify-center bg-background px-8 py-12 sm:px-16">
        <div className="mx-auto w-full max-w-sm">
          <h2 className="font-display text-3xl font-semibold tracking-tight text-foreground">Welcome back</h2>
          <p className="mb-8 mt-1.5 text-sm text-muted-fg">Sign in to the document intelligence workspace.</p>

          <form onSubmit={onSubmit} className="flex flex-col gap-4">
            <label className="text-sm font-semibold text-foreground">
              Username
              <Input className="mt-1.5" value={username} onChange={(e) => setU(e.target.value)} autoComplete="username" autoFocus required />
            </label>

            <div className="text-sm font-semibold text-foreground">
              Password
              <div className="relative mt-1.5">
                <Input
                  type={show ? "text" : "password"}
                  value={password}
                  onChange={(e) => setP(e.target.value)}
                  autoComplete="current-password"
                  required
                  className="pr-16"
                  aria-label="Password"
                />
                <button
                  type="button"
                  onClick={() => setShow((s) => !s)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 font-mono text-xs font-semibold text-primary"
                >
                  <span className="sr-only">{show ? "Hide password" : "Show password"}</span>
                  <span aria-hidden>{show ? "HIDE" : "SHOW"}</span>
                </button>
              </div>
            </div>

            <div className="flex items-center justify-between text-sm">
              <label className="flex cursor-pointer items-center gap-2 text-muted-fg">
                <input type="checkbox" className="h-4 w-4 accent-[rgb(13_148_136)]" /> Keep me signed in
              </label>
            </div>

            {error && <p role="alert" className="text-sm text-danger">{error}</p>}

            <Button type="submit" loading={login.isPending} className="mt-1 w-full">Sign in</Button>
          </form>

          <p className="mt-7 text-center text-xs text-tertiary-fg">🔒 Audited access · role-based permissions</p>
        </div>
      </div>
    </main>
  );
}
