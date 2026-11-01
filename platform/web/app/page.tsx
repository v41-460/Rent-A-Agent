"use client";

import { useEffect, useState } from "react";
import { AgentCard } from "@/components/AgentCard";
import { Notice } from "@/components/Notice";
import { api, type AgentCard as Agent } from "@/lib/api";

export default function Marketplace() {
  const [agents, setAgents] = useState<Agent[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .agents()
      .then((r) => setAgents(r.agents))
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <div className="space-y-8">
      <section className="space-y-3">
        <h1 className="text-3xl font-bold sm:text-4xl">Helpers for everyday tasks</h1>
        <p className="text-xl text-muted">
          Each helper does one job well. Pick one, rent it, and it gets to work for you.
        </p>
      </section>
      {error ? <Notice level="danger">{error}</Notice> : null}
      {agents === null && !error ? <p className="text-lg">Loading helpers…</p> : null}
      {agents?.length === 0 ? <Notice>No helpers yet. Check back soon.</Notice> : null}
      {agents && agents.length > 0 ? (
        <ul className="grid gap-5 sm:grid-cols-2">
          {agents.map((a) => (
            <li key={a.slug}>
              <AgentCard agent={a} />
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
