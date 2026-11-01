"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { Notice } from "./Notice";
import { api } from "@/lib/api";

/** Only allow going back to a page on this site after login. */
export function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const signup = mode === "signup";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (signup) await api.signup(email, password, name);
      else await api.login(email, password);
      window.location.assign(next);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  const other = signup ? "/login" : "/signup";
  return (
    <div className="mx-auto max-w-md space-y-6">
      <h1 className="text-3xl font-bold">{signup ? "Create your account" : "Log in"}</h1>
      {error ? <Notice level="danger">{error}</Notice> : null}
      <form onSubmit={submit} className="space-y-5">
        {signup ? (
          <div className="space-y-1">
            <label htmlFor="name" className="block font-semibold">
              Your first name
            </label>
            <input id="name" className="field" required autoComplete="given-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
        ) : null}
        <div className="space-y-1">
          <label htmlFor="email" className="block font-semibold">
            Email address
          </label>
          <input id="email" type="email" className="field" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="space-y-1">
          <label htmlFor="password" className="block font-semibold">
            Password
          </label>
          <input
            id="password"
            type={showPassword ? "text" : "password"}
            className="field"
            required
            minLength={signup ? 8 : undefined}
            autoComplete={signup ? "new-password" : "current-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {signup ? <p className="text-base text-muted">At least 8 characters.</p> : null}
          <label className="flex items-center gap-2 text-base">
            <input type="checkbox" className="h-5 w-5" checked={showPassword} onChange={(e) => setShowPassword(e.target.checked)} />
            Show password
          </label>
        </div>
        <button type="submit" className="btn btn-primary w-full" disabled={busy}>
          {busy ? "One moment…" : signup ? "Create account" : "Log in"}
        </button>
      </form>
      <p className="text-lg">
        {signup ? "Already have an account? " : "New here? "}
        <Link href={`${other}?next=${encodeURIComponent(next)}`} className="font-semibold text-action underline">
          {signup ? "Log in" : "Create an account"}
        </Link>
      </p>
    </div>
  );
}
