"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Notice } from "@/components/Notice";
import { api, ApiError, type AgentCard } from "@/lib/api";
import { iconText } from "@/lib/icon";

export default function MyAgents() {
  const [agents, setAgents] = useState<AgentCard[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    api
      .myAgents()
      .then((r) => setAgents(r.agents))
      .catch((e: ApiError) => setError(e));
  }, []);

  if (error?.code === "not_logged_in") {
    return (
      <Notice>
        Please{" "}
        <Link href="/login?next=/my-agents" className="font-semibold underline">
          log in
        </Link>{" "}
        to see your helpers.
      </Notice>
    );
  }
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">My helpers</h1>
      {error ? <Notice level="danger">{error.message}</Notice> : null}
      {agents === null && !error ? <p className="text-lg">Loading…</p> : null}
      {agents?.length === 0 ? (
        <Notice>
          You haven't rented any helpers yet.{" "}
          <Link href="/" className="font-semibold underline">
            See all helpers
          </Link>
        </Notice>
      ) : null}
      <ul className="space-y-4">
        {agents?.map((a) => (
          <li key={a.slug} className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border-2 border-line bg-card p-5">
            <div className="flex items-center gap-3">
              <span aria-hidden="true" className="text-4xl">
                {iconText(a.icon)}
              </span>
              <div>
                <p className="text-xl font-bold">{a.name}</p>
                <p className="text-base text-muted">{a.price_text}</p>
              </div>
            </div>
            <Link href={`/agents/${a.slug}/use`} className="btn btn-primary">
              Open
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
