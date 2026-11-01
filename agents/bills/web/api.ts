// Calls to the Bills agent's own endpoints, through the platform (which checks the person
// is logged in and has rented Bills). Amounts arrive as strings ("1450.00") so nothing is
// rounded on the way; they are only formatted for display, never calculated with.

export type Flag = { kind: string; severity: "review" | "info"; message: string };

export type Bill = {
  id: string;
  payee: string;
  frequency: string;
  status: "active" | "possible" | "stopped";
  typical_amount: string;
  min_amount: string;
  max_amount: string;
  last_amount: string;
  last_date: string;
  next_due: string | null;
  next_due_earliest: string | null;
  next_due_latest: string | null;
  confidence: number;
  occurrences: number;
  account_count: number;
  category: string | null;
  reasons: string[];
  flags: Flag[];
  bucket: "needs_attention" | "due_soon" | "upcoming" | "stopped";
};

export type BillsResponse =
  | { status: "not_run" }
  | {
      status: "ready";
      as_of: string;
      history_days: number;
      transaction_count: number;
      bills: Bill[];
      flags: Flag[];
    };

export type SyncResponse = {
  status: "ready" | "still_loading" | "reconnect_needed" | "not_connected";
  message?: string;
};

export type Connection = {
  connected: boolean;
  bank_available: boolean;
  banks: { name: string; status: "ok" | "reconnect_needed" | "sample"; last_synced_at: string | null }[];
};

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

const FALLBACK =
  "Something didn't work, but nothing has changed in your bank account. Let's try again.";

export function billsApi(base: string) {
  async function call<T>(path: string, init?: RequestInit): Promise<T> {
    let response: Response;
    try {
      response = await fetch(base + path, {
        ...init,
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", ...init?.headers },
      });
    } catch {
      throw new ApiError("offline", "We couldn't reach the internet. Please check your connection.");
    }
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const d = body?.detail;
      throw new ApiError(d?.code ?? "unknown", typeof d?.message === "string" ? d.message : FALLBACK);
    }
    return body as T;
  }
  const post = <T>(path: string, body: unknown = {}) =>
    call<T>(path, { method: "POST", body: JSON.stringify(body) });

  return {
    linkToken: (reconnect = false) => post<{ link_token: string }>("/link/token", { reconnect }),
    exchange: (public_token: string, institution: unknown) =>
      post<{ connected: boolean; institution_name: string }>("/link/exchange", {
        public_token,
        institution,
      }),
    reconnected: () => post<{ ok: boolean }>("/link/reconnected"),
    linkEvent: (event: "opened" | "exit" | "error", details: Record<string, unknown> = {}) =>
      post("/link/event", { event, ...details }).catch(() => undefined),
    connection: () => call<Connection>("/connection"),
    sample: () => post<{ status: string; bill_count: number }>("/sample"),
    disconnect: () => post<{ ok: boolean }>("/disconnect"),
    sync: () => post<SyncResponse>("/sync"),
    bills: () => call<BillsResponse>("/bills"),
  };
}

export type BillsApi = ReturnType<typeof billsApi>;
