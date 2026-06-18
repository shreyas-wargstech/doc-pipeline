"use client";
import { motion } from "motion/react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { LoginBrandPanel } from "@/components/auth/LoginBrandPanel";
import { useLogin } from "@/hooks/useAuth";
import { ApiError } from "@/lib/api";
import { DEMO_PASSWORD, DEMO_USERS, SHOW_DEMO_LOGINS } from "@/lib/demo-users";

export default function LoginPage() {
  const router = useRouter();
  const login = useLogin();
  const [username, setU] = useState("");
  const [password, setP] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const signIn = async (u: string, p: string) => {
    if (login.isPending) return;
    setError(null);
    try {
      await login.mutateAsync({ username: u, password: p });
      router.replace("/");
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "Invalid username or password."
          : "Sign-in failed. Check your connection or try again.",
      );
    }
  };

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void signIn(username, password);
  };

  return (
    <main className="grid min-h-dvh md:grid-cols-2">
      <LoginBrandPanel />

      <div className="flex flex-col justify-center bg-background px-8 py-12 sm:px-16">
        <div className="mx-auto w-full max-w-sm">
          <h2 className="font-display text-3xl font-semibold tracking-tight text-foreground">Welcome back</h2>
          <p className="mb-8 mt-1.5 text-sm text-muted-foreground">Sign in to the document intelligence workspace.</p>

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
              <label className="flex cursor-pointer items-center gap-2 text-muted-foreground">
                <input type="checkbox" className="h-4 w-4 accent-primary" /> Keep me signed in
              </label>
            </div>

            {error && <p role="alert" className="text-sm text-danger">{error}</p>}

            <Button type="submit" loading={login.isPending} className="mt-1 w-full">Sign in</Button>
          </form>

          <p className="mt-7 text-center text-xs text-tertiary-fg">🔒 Audited access · role-based permissions</p>

          {SHOW_DEMO_LOGINS && (
            <div className="mt-8 rounded-xl border border-border bg-surface-alt/60 p-4">
              <p className="mb-3 text-center font-mono text-[10.5px] uppercase tracking-widest text-tertiary-fg">
                Demo accounts · dev only
              </p>
              <div className="grid grid-cols-2 gap-2">
                {DEMO_USERS.map((u, i) => (
                  <motion.button
                    key={u.username}
                    type="button"
                    disabled={login.isPending}
                    onClick={() => void signIn(u.username, DEMO_PASSWORD)}
                    initial={{ opacity: 0, y: 8, filter: "blur(4px)" }}
                    animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                    transition={{ delay: i * 0.06, duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                    className="flex flex-col items-start rounded-lg border border-border-strong bg-surface px-3 py-2 text-left transition-colors hover:border-primary disabled:opacity-50"
                  >
                    <span className="text-sm font-semibold text-foreground">{u.name}</span>
                    <span className="text-xs text-muted-foreground">{u.role}</span>
                  </motion.button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
