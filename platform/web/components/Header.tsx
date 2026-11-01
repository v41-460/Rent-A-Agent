"use client";

import Link from "next/link";
import { api } from "@/lib/api";
import { useUser } from "@/lib/useUser";

export function Header() {
  const user = useUser();
  return (
    <header className="border-b-2 border-line bg-card">
      <nav className="mx-auto flex max-w-4xl flex-wrap items-center justify-between gap-3 px-4 py-3">
        <Link href="/" className="text-xl font-bold text-ink no-underline">
          🤝 Rent an Agent
        </Link>
        <div className="flex flex-wrap items-center gap-4 text-lg">
          <Link href="/" className="underline">
            All helpers
          </Link>
          {user ? (
            <>
              <Link href="/my-agents" className="underline">
                My helpers
              </Link>
              <button
                type="button"
                className="underline"
                onClick={async () => {
                  await api.logout().catch(() => undefined);
                  window.location.assign("/");
                }}
              >
                Log out
              </button>
            </>
          ) : user === null ? (
            <>
              <Link href="/login" className="underline">
                Log in
              </Link>
              <Link href="/signup" className="btn btn-primary">
                Sign up
              </Link>
            </>
          ) : null}
        </div>
      </nav>
    </header>
  );
}
