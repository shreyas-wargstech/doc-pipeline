"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { useLogin } from "@/hooks/useAuth";

export default function LoginPage() {
  const router = useRouter();
  const login = useLogin();
  const [username, setU] = useState("");
  const [password, setP] = useState("");
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try { await login.mutateAsync({ username, password }); router.replace("/"); }
    catch { setError("Invalid username or password."); }
  };

  return (
    <main className="flex min-h-dvh items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <h1 className="mb-1 text-lg font-semibold text-foreground">Doc Pipeline</h1>
        <p className="mb-5 text-sm text-muted-fg">Sign in to the operations dashboard.</p>
        <form onSubmit={onSubmit} className="flex flex-col gap-3">
          <label className="text-sm font-medium text-foreground">Username
            <Input className="mt-1" value={username} onChange={(e) => setU(e.target.value)} autoComplete="username" required />
          </label>
          <label className="text-sm font-medium text-foreground">Password
            <Input className="mt-1" type="password" value={password} onChange={(e) => setP(e.target.value)} autoComplete="current-password" required />
          </label>
          {error && <p role="alert" className="text-sm text-danger">{error}</p>}
          <Button type="submit" loading={login.isPending} className="mt-1 w-full">Sign in</Button>
        </form>
      </Card>
    </main>
  );
}
