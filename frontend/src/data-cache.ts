import type { State } from "./types";

const key = (experiment: string) => `survival:confirmed:${experiment}`;

export function confirmedState(value: unknown, experiment: string): value is State {
  if (!value || typeof value !== "object") return false;
  const s = value as State;
  return s.id === experiment && s.mode === "live" &&
    Number.isFinite(Date.parse(s.updated_at)) && Array.isArray(s.agents) &&
    !!s.fx && !!s.markets;
}

// Only public projections received from Supabase are cached; never demo data.
// Storage may be disabled or full: the live connection must still work.
export function readConfirmed(experiment: string): State | null {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(key(experiment)) || "null");
    return confirmedState(value, experiment) ? value : null;
  } catch { return null; }
}

export function cacheConfirmed(experiment: string, value: State): void {
  if (!confirmedState(value, experiment)) return;
  try { localStorage.setItem(key(experiment), JSON.stringify(value)); } catch { /* optional cache */ }
}

export function connectionError(error: unknown, timedOut: boolean): string {
  if (timedOut) return "Supabase ne répond pas dans le délai prévu. Nouvelle tentative automatique dans une minute";
  if (error && typeof error === "object" && "status" in error && error.status === 402)
    return "Supabase a restreint le projet pour dépassement de quota";
  return "Le service de données est temporairement inaccessible. Nouvelle tentative automatique dans une minute";
}
