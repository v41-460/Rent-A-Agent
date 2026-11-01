// Calls to the platform backend (forwarded by next.config.ts). Errors carry a plain
// message from the backend that is safe to show to the user as-is.
import type { RunResponse } from "@shared/agent-interface";

export type User = { id: string; email: string; display_name: string };

export type AgentCard = {
  slug: string;
  name: string;
  description: string;
  long_description?: string;
  icon: string;
  pricing: { model: "free" | "monthly" | "one_time"; amount_cents: number; currency: string };
  price_text: string;
  status: "available" | "coming_soon";
  rentable: boolean;
  rented: boolean;
  has_custom_page: boolean;
};

export type RentResult = {
  rental_id: string;
  already_rented: boolean;
  payment: { id: string; amount_cents: number; provider: "mock"; test_mode: true } | null;
};

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

const FALLBACK = "Something didn't work. Please try again in a minute.";

export async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, "network", "We couldn't reach Rent an Agent. Check your internet and try again.");
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = body?.detail;
    const message = typeof d?.message === "string" ? d.message : FALLBACK;
    throw new ApiError(res.status, d?.code ?? "unknown", message);
  }
  return body as T;
}

const post = (body?: unknown): RequestInit => ({
  method: "POST",
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const api = {
  me: () => call<{ user: User | null }>("/api/auth/me"),
  signup: (email: string, password: string, display_name: string) =>
    call<{ user: User }>("/api/auth/signup", post({ email, password, display_name })),
  login: (email: string, password: string) =>
    call<{ user: User }>("/api/auth/login", post({ email, password })),
  logout: () => call<{ ok: true }>("/api/auth/logout", post()),
  agents: () => call<{ agents: AgentCard[] }>("/api/agents"),
  agent: (slug: string) => call<{ agent: AgentCard }>(`/api/agents/${encodeURIComponent(slug)}`),
  myAgents: () => call<{ agents: AgentCard[] }>("/api/rentals"),
  rent: (slug: string) => call<RentResult>(`/api/agents/${encodeURIComponent(slug)}/rent`, post()),
  run: (slug: string, input: Record<string, unknown> = {}) =>
    call<RunResponse>(`/api/agents/${encodeURIComponent(slug)}/run`, post({ input })),
};
