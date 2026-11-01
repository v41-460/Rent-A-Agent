import Link from "next/link";
import type { AgentCard as Agent } from "@/lib/api";
import { iconText } from "@/lib/icon";

export function AgentCard({ agent }: { agent: Agent }) {
  return (
    <Link
      href={`/agents/${agent.slug}`}
      className="flex h-full flex-col gap-3 rounded-2xl border-2 border-line bg-card p-5 text-ink no-underline hover:border-action"
    >
      <div className="flex items-center gap-3">
        <span aria-hidden="true" className="text-4xl">
          {iconText(agent.icon)}
        </span>
        <h2 className="text-xl font-bold">{agent.name}</h2>
      </div>
      <p className="flex-1 text-lg">{agent.description}</p>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-lg font-semibold">{agent.price_text}</span>
        {agent.rented ? (
          <span className="rounded-full bg-calm-bg px-3 py-1 text-base font-semibold text-calm">
            You have this
          </span>
        ) : !agent.rentable ? (
          <span className="rounded-full bg-soon-bg px-3 py-1 text-base font-semibold text-soon">
            Coming soon
          </span>
        ) : null}
      </div>
    </Link>
  );
}
