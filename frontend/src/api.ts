function resolveApiBase(): string {
  // Explicit override wins.
  const env = (import.meta as any).env?.VITE_API_BASE;
  if (env) return env;

  // Default: same origin. In dev, Vite proxies /api and /ws to the backend
  // (see vite.config.ts) so the browser stays on a single origin. In prod,
  // set VITE_API_BASE to your backend URL.
  if (typeof window !== "undefined") {
    return window.location.origin;
  }
  return "http://localhost:8000";
}

export const API_BASE = resolveApiBase();

// ws:// or wss:// matching the page protocol, same host.
export const WS_BASE = API_BASE.replace(/^http/, "ws");

import { getAuthToken } from "./auth";

async function authHeaders(): Promise<HeadersInit> {
  const token = await getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function getAgents() {
  const r = await fetch(`${API_BASE}/api/agents`, { headers: await authHeaders() });
  return r.json();
}

export async function getHealth() {
  // health is open; no auth needed
  const r = await fetch(`${API_BASE}/api/health`);
  return r.json();
}
