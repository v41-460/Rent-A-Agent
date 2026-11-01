"use client";

import { useCallback, useEffect, useState } from "react";
import { usePlaidLink, type PlaidLinkOnExit, type PlaidLinkOnSuccess } from "react-plaid-link";

import { ApiError, type BillsApi } from "./api";
import { linkExitMessage } from "./linkErrors";
import { Notice } from "./Notice";

type Props = {
  api: BillsApi;
  label: string;
  // Sign in to an already-connected bank again (Plaid Link "update mode").
  reconnect?: boolean;
  onConnected: () => void;
};

export function ConnectButton({ api, label, reconnect = false, onConnected }: Props) {
  const [token, setToken] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const onSuccess = useCallback<PlaidLinkOnSuccess>(
    async (publicToken, metadata) => {
      setToken(null);
      try {
        if (reconnect) {
          await api.reconnected();
        } else {
          if (!publicToken) throw new ApiError("link_expired", linkExitMessage({}));
          await api.exchange(publicToken, metadata.institution);
        }
        onConnected();
      } catch (error) {
        setMessage(error instanceof ApiError ? error.message : linkExitMessage({}));
        setBusy(false);
      }
    },
    [api, reconnect, onConnected],
  );

  const onExit = useCallback<PlaidLinkOnExit>((error, metadata) => {
    void api.linkEvent(error ? "error" : "exit", {
      error_code: error?.error_code,
      error_type: error?.error_type,
      link_status: metadata.status,
      institution_name: metadata.institution?.name,
    });
    setToken(null);
    setBusy(false);
    setMessage(linkExitMessage(error));
  }, [api]);

  const { open, ready } = usePlaidLink({ token, onSuccess, onExit });

  useEffect(() => {
    if (token && ready) open();
  }, [token, ready, open]);

  async function start() {
    setMessage(null);
    setBusy(true);
    try {
      const { link_token } = await api.linkToken(reconnect);
      void api.linkEvent("opened");
      setToken(link_token);
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : linkExitMessage({}));
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <button
        type="button"
        onClick={start}
        disabled={busy}
        className="w-full rounded-xl bg-action px-6 py-4 text-xl font-semibold text-white shadow-sm transition hover:bg-action-dark disabled:cursor-wait disabled:opacity-70 sm:w-auto"
      >
        {busy ? "Opening your bank's sign-in page…" : label}
      </button>
      {message && <Notice tone="calm">{message}</Notice>}
    </div>
  );
}
