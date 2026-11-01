"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import type { RunResponse } from "@shared/agent-interface";
import { Blocks } from "@/components/Blocks";
import { Notice } from "@/components/Notice";
import { api, ApiError } from "@/lib/api";
import { agentApiBase, customPages } from "@/lib/customPages";

export default function UseAgent() {
  const { slug } = useParams<{ slug: string }>();
  const Custom = customPages[slug];
  return Custom ? <CustomAgentPage slug={slug} Page={Custom} /> : <BlocksAgentPage slug={slug} />;
}

/** Agents with their own page: check the person rented it, then show the page. */
function CustomAgentPage({ slug, Page }: { slug: string; Page: (typeof customPages)[string] }) {
  const [state, setState] = useState<"checking" | "ok" | ApiError>("checking");
  useEffect(() => {
    api
      .agent(slug)
      .then((r) =>
        setState(
          r.agent.rented
            ? "ok"
            : new ApiError(403, "not_rented", "You'll need to rent this helper before using it."),
        ),
      )
      .catch((e: ApiError) => setState(e));
  }, [slug]);
  return (
    <div className="space-y-6">
      <BackLink />
      {state === "checking" ? <p className="text-lg">Loading…</p> : null}
      {state instanceof ApiError ? <ErrorNotice error={state} slug={slug} /> : null}
      {state === "ok" ? <Page apiBase={agentApiBase(slug)} /> : null}
    </div>
  );
}

function BackLink() {
  return (
    <Link href="/my-agents" className="text-lg underline">
      ← My helpers
    </Link>
  );
}

function ErrorNotice({ error, slug }: { error: ApiError; slug: string }) {
  return (
    <Notice level="danger">
      {error.message}{" "}
      {error.code === "not_logged_in" ? (
        <Link href={`/login?next=/agents/${slug}/use`} className="font-semibold underline">
          Log in
        </Link>
      ) : error.code === "not_rented" ? (
        <Link href={`/agents/${slug}`} className="font-semibold underline">
          See this helper
        </Link>
      ) : null}
    </Notice>
  );
}

function BlocksAgentPage({ slug }: { slug: string }) {
  const [result, setResult] = useState<RunResponse | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(true);

  const send = useCallback(
    async (input: Record<string, unknown>) => {
      setBusy(true);
      setError(null);
      try {
        setResult(await api.run(slug, input));
      } catch (e) {
        setError(e instanceof ApiError ? e : new ApiError(0, "unknown", "Something didn't work."));
      } finally {
        setBusy(false);
      }
    },
    [slug],
  );

  useEffect(() => {
    void send({});
  }, [send]);

  return (
    <div className="space-y-6">
      <BackLink />
      {error ? <ErrorNotice error={error} slug={slug} /> : null}
      {busy && !result ? <p className="text-lg">Working on it…</p> : null}
      {result ? <Blocks blocks={result.blocks} onSend={send} busy={busy} /> : null}
    </div>
  );
}
