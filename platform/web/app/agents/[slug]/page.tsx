"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Notice } from "@/components/Notice";
import { api, ApiError, type AgentCard } from "@/lib/api";
import { iconText } from "@/lib/icon";
import { useUser } from "@/lib/useUser";

type Step = "view" | "checkout" | "renting";

export default function AgentDetail() {
  const { slug } = useParams<{ slug: string }>();
  const router = useRouter();
  const user = useUser();
  const [agent, setAgent] = useState<AgentCard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState<Step>("view");

  useEffect(() => {
    api
      .agent(slug)
      .then((r) => setAgent(r.agent))
      .catch((e: Error) => setError(e.message));
  }, [slug]);

  if (error && !agent) return <Notice level="danger">{error}</Notice>;
  if (!agent) return <p className="text-lg">Loading…</p>;

  const usePath = `/agents/${agent.slug}/use`;
  const free = agent.pricing.model === "free";

  function startRent() {
    if (user === null) {
      router.push(`/signup?next=${encodeURIComponent(`/agents/${slug}`)}`);
      return;
    }
    if (free) void confirmRent();
    else setStep("checkout");
  }

  async function confirmRent() {
    setStep("renting");
    setError(null);
    try {
      await api.rent(slug);
      router.push(usePath);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something didn't work. Please try again.");
      setStep("view");
    }
  }

  return (
    <article className="space-y-6">
      <Link href="/" className="text-lg underline">
        ← All helpers
      </Link>
      <div className="flex items-center gap-4">
        <span aria-hidden="true" className="text-6xl">
          {iconText(agent.icon)}
        </span>
        <div>
          <h1 className="text-3xl font-bold">{agent.name}</h1>
          <p className="text-xl font-semibold">{agent.price_text}</p>
        </div>
      </div>
      <p className="text-xl">{agent.description}</p>
      {agent.long_description ? (
        <p className="whitespace-pre-line text-lg text-muted">{agent.long_description}</p>
      ) : null}
      {error ? <Notice level="danger">{error}</Notice> : null}

      {agent.rented ? (
        <Link href={usePath} className="btn btn-primary">
          Open {agent.name}
        </Link>
      ) : !agent.rentable ? (
        <Notice level="warning">This helper is coming soon. It can't be rented yet.</Notice>
      ) : step === "view" ? (
        <button type="button" className="btn btn-primary text-xl" onClick={startRent} disabled={user === undefined}>
          Rent {free ? "for free" : `for ${agent.price_text}`}
        </button>
      ) : (
        <section aria-labelledby="checkout" className="space-y-4 rounded-2xl border-2 border-action bg-card p-6">
          <h2 id="checkout" className="text-2xl font-bold">
            Confirm your rental
          </h2>
          <p className="text-lg">
            You're renting <strong>{agent.name}</strong> for <strong>{agent.price_text}</strong>.
          </p>
          <Notice level="warning">
            Test mode: this is a pretend payment. No card is needed and nothing is charged.
          </Notice>
          <div className="flex flex-wrap gap-3">
            <button type="button" className="btn btn-primary" onClick={confirmRent} disabled={step === "renting"}>
              {step === "renting" ? "One moment…" : "Confirm and rent"}
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => setStep("view")} disabled={step === "renting"}>
              Go back
            </button>
          </div>
        </section>
      )}
    </article>
  );
}
