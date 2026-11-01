/**
 * Shared agent interface, TypeScript side. Mirrors src/rent_agent_interface/models.py.
 * The JSON Schemas in ../schema/ are generated from the Python models and are the
 * source of truth; change Python first, then update this file to match.
 * Changes need Vai's approval (see AGENTS.md).
 */

export const INTERFACE_VERSION = "1";

export type Owner = "claude" | "codex" | "grok" | "hermes";

export interface Pricing {
  model: "free" | "monthly" | "one_time";
  amount_cents: number;
  currency: "USD";
}

export interface Manifest {
  interface_version: "1";
  slug: string;
  name: string;
  description: string;
  long_description: string;
  icon: string;
  owner: Owner;
  version: string;
  pricing: Pricing;
  status: "available" | "coming_soon";
  location: "local" | "remote";
  base_url: string | null;
  has_custom_page: boolean;
}

export interface HeadingBlock { type: "heading"; text: string }
export interface TextBlock { type: "text"; text: string }
export interface NoticeBlock {
  type: "notice";
  level: "info" | "success" | "warning" | "danger";
  text: string;
}
export interface Item { title: string; subtitle: string; value: string }
export interface ItemsBlock { type: "items"; items: Item[]; empty_text: string }
export interface TableBlock { type: "table"; columns: string[]; rows: string[][] }
export interface LinkBlock { type: "link"; label: string; url: string }
export interface Action {
  label: string;
  input: Record<string, unknown>;
  style: "primary" | "secondary" | "danger";
  confirm: string | null;
}
export interface ActionsBlock { type: "actions"; actions: Action[] }
export interface FormField {
  name: string;
  label: string;
  kind: "text" | "number" | "date" | "textarea" | "email";
  required: boolean;
  help: string;
}
export interface FormBlock { type: "form"; fields: FormField[]; submit_label: string }

export type Block =
  | HeadingBlock
  | TextBlock
  | NoticeBlock
  | ItemsBlock
  | TableBlock
  | LinkBlock
  | ActionsBlock
  | FormBlock;

export interface RunUser { id: string; display_name: string }

export interface RunRequest {
  user: RunUser;
  rental_id: string;
  input: Record<string, unknown>;
}

export interface RunResponse {
  status: "ok" | "needs_input" | "error";
  message: string;
  blocks: Block[];
}

export interface Health { ok: boolean; detail: string }
