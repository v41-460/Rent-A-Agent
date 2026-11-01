"use client";

// The Bills page, shown by the platform at /agents/bills/use (see platform/web/lib/customPages.tsx).
import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiError, billsApi, type Bill, type BillsResponse, type Connection } from "./api";
import { BillCard } from "./BillCard";
import { ConnectButton } from "./ConnectButton";
import { longDate } from "./format";
import { Notice } from "./Notice";

type Phase = "loading" | "waiting" | "ready" | "not_connected";
type Ready = Extract<BillsResponse, { status: "ready" }>;

const SECTIONS: { bucket: Bill["bucket"]; title: string; note: string; tone: string }[] = [
  {
    bucket: "needs_attention",
    title: "Needs your attention",
    note: "I'm not sure about these, or something looks different from usual. Please take a look.",
    tone: "border-attention",
  },
  { bucket: "due_soon", title: "Due soon", note: "Coming up in the next 7 days.", tone: "border-soon" },
  { bucket: "upcoming", title: "Upcoming", note: "Nothing for you to do.", tone: "border-calm" },
];

const WAIT_MS = 5000;
const MAX_WAITS = 24;

export default function BillsPage({ apiBase }: { apiBase: string }) {
  const api = useMemo(() => billsApi(apiBase), [apiBase]);
  const [connection, setConnection] = useState<Connection | null>(null);
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState<Phase>("loading");
  const [data, setData] = useState<Ready | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reconnect, setReconnect] = useState(false);

  const refresh = useCallback(async (waits = 0) => {
    setNotice(null);
    const connection = await api.connection().catch(() => null);
    setConnection(connection);
    if (connection && !connection.connected) {
      setPhase("not_connected");
      return;
    }
    try {
      const sync = await api.sync();
      if (sync.status === "still_loading" && waits < MAX_WAITS) {
        setPhase("waiting");
        setTimeout(() => void refresh(waits + 1), WAIT_MS);
        return;
      }
      setReconnect(sync.status === "reconnect_needed");
      if (sync.message) setNotice(sync.message);
    } catch (error) {
      // Couldn't refresh. Still show what we found last time.
      setNotice(error instanceof ApiError ? error.message : null);
    }
    try {
      const bills = await api.bills();
      if (bills.status === "ready") setData(bills);
    } catch (error) {
      setNotice(error instanceof ApiError ? error.message : null);
    }
    setPhase("ready");
  }, [api]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const afterReconnect = useCallback(() => {
    setReconnect(false);
    setPhase("loading");
    void refresh();
  }, [refresh]);

  async function startPractice() {
    setBusy(true);
    setNotice(null);
    try {
      await api.sample();
      setPhase("loading");
      await refresh();
    } catch (error) {
      setNotice(error instanceof ApiError ? error.message : null);
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    const ok = window.confirm(
      "Disconnect and forget your bank? Bills will forget everything it found. You can connect again any time.",
    );
    if (!ok) return;
    setBusy(true);
    await api.disconnect().catch(() => undefined);
    setData(null);
    setBusy(false);
    setPhase("loading");
    await refresh();
  }

  if (phase === "not_connected") {
    return (
      <div className="space-y-8">
        <header className="space-y-3">
          <h1 className="text-4xl font-bold">Let&apos;s find your bills</h1>
          <p className="text-xl">
            Connect your bank once and I&apos;ll look through your payments for bills you pay
            regularly. I can only look. I can never move money.
          </p>
        </header>
        {notice && <Notice>{notice}</Notice>}
        <section className="space-y-3">
          {connection?.bank_available === false ? (
            <Notice>The bank connection isn&apos;t set up on this server yet.</Notice>
          ) : (
            <>
              <ConnectButton api={api} label="Connect my bank" onConnected={afterReconnect} />
              <p className="text-base text-muted">
                This is a practice version with pretend banks. When the sign-in page opens, pick
                any bank and use the username <strong>user_good</strong> and password{" "}
                <strong>pass_good</strong>.
              </p>
            </>
          )}
        </section>
        <section className="space-y-3 border-t-2 border-line pt-6">
          <h2 className="text-2xl font-bold">Just want to look around?</h2>
          <p className="text-lg">Try Bills with a made-up household. No bank needed.</p>
          <button type="button" className="btn btn-secondary" onClick={startPractice} disabled={busy}>
            {busy ? "One moment…" : "Use the practice bank"}
          </button>
        </section>
      </div>
    );
  }

  if (phase === "loading" || phase === "waiting") {
    return (
      <div className="space-y-4" role="status" aria-live="polite">
        <h1 className="text-4xl font-bold">Looking through your payments…</h1>
        <p className="text-xl text-muted">
          {phase === "waiting"
            ? "Your bank is still sending your transactions. The first time can take a minute or two. You don't need to do anything."
            : "This only takes a moment."}
        </p>
      </div>
    );
  }

  const bills = data?.bills ?? [];
  const stopped = bills.filter((b) => b.bucket === "stopped");
  const active = bills.filter((b) => b.bucket !== "stopped");

  return (
    <div className="space-y-10">
      <header className="space-y-2">
        <h1 className="text-4xl font-bold">Your bills</h1>
        {data && (
          <p className="text-lg text-muted">
            Based on {data.transaction_count.toLocaleString("en-US")} transactions over the last{" "}
            {data.history_days} days. Checked on {longDate(data.as_of)}.
          </p>
        )}
      </header>

      {notice && <Notice>{notice}</Notice>}
      {reconnect && <ConnectButton api={api} label="Sign in to my bank again" reconnect onConnected={afterReconnect} />}

      {data?.flags.map((flag) => (
        <Notice key={flag.kind + flag.message} tone="attention">
          {flag.message}
        </Notice>
      ))}

      {data && active.length === 0 && (
        <p className="text-xl">
          I haven&apos;t found any regular bills yet. I&apos;ll keep looking as new payments come in.
        </p>
      )}

      {SECTIONS.map((section) => {
        const items = active.filter((b) => b.bucket === section.bucket);
        if (items.length === 0) return null;
        return (
          <section key={section.bucket} aria-labelledby={section.bucket} className="space-y-4">
            <div className={`border-l-8 pl-4 ${section.tone}`}>
              <h2 id={section.bucket} className="text-3xl font-bold">
                {section.title} <span className="text-muted">({items.length})</span>
              </h2>
              <p className="text-lg text-muted">{section.note}</p>
            </div>
            <ul className="space-y-4">
              {items.map((bill) => (
                <BillCard key={bill.id} bill={bill} asOf={data!.as_of} />
              ))}
            </ul>
          </section>
        );
      })}

      {stopped.length > 0 && (
        <details className="text-lg">
          <summary className="cursor-pointer font-semibold">
            Bills that seem to have stopped ({stopped.length})
          </summary>
          <ul className="mt-4 space-y-4">
            {stopped.map((bill) => (
              <BillCard key={bill.id} bill={bill} asOf={data!.as_of} />
            ))}
          </ul>
        </details>
      )}

      <footer className="space-y-3 border-t-2 border-line pt-6 text-lg">
        {connection?.banks.map((b) => (
          <p key={b.name}>
            Connected: <strong>{b.name}</strong>
            {b.status === "sample" ? " (made-up data)" : ""}
          </p>
        ))}
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            className="btn btn-secondary"
            disabled={busy}
            onClick={() => {
              setPhase("loading");
              void refresh();
            }}
          >
            Check again
          </button>
          <button type="button" className="btn btn-secondary" disabled={busy} onClick={disconnect}>
            Disconnect my bank
          </button>
        </div>
      </footer>
    </div>
  );
}
