// Agents that ship their own page (manifest "has_custom_page": true) are listed here.
// The page lives in the agent's folder (agents/<slug>/web/) and gets the base URL of its
// own endpoints, which the platform serves only to people who rented it.
import dynamic from "next/dynamic";
import type { ComponentType } from "react";

export type CustomPageProps = { apiBase: string };

const loading = () => <p className="text-lg">Loading…</p>;

export const customPages: Record<string, ComponentType<CustomPageProps>> = {
  bills: dynamic(() => import("../../../agents/bills/web/BillsPage"), { ssr: false, loading }),
};

export function agentApiBase(slug: string): string {
  return `/api/agents/${encodeURIComponent(slug)}/x`;
}
