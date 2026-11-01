"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import type { RunResponse } from "@shared/agent-interface";
import { Blocks } from "@/components/Blocks";
import { Notice } from "@/components/Notice";
import { api, ApiError } from "@/lib/api";

export default function UseAgent() {
  const { slug } = useParams<{ slug: string }>();
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
      <Link href="/my-agents" className="text-lg underline">
        ← My helpers
      </Link>
      {error ? (
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
      ) : null}
      {busy && !result ? <p className="text-lg">Working on it…</p> : null}
      {result ? <Blocks blocks={result.blocks} onSend={send} busy={busy} /> : null}
    </div>
  );
}
