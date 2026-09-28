/* REST client for the AetherQuant FastAPI backend.
 * Dev: Vite proxies /api → http://127.0.0.1:8700 (vite.config.ts).
 * Prod: set VITE_API_BASE to the deployed API origin. */

import type { AlphaFactor, SentinelCheck, SentinelVerdict } from "../types";

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) throw new Error(`${path} → ${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export interface RunMetrics {
  sharpe: number;
  annRetPct: number;
  maxDrawdownPct: number;
  winRatePct: number;
  finalNav: number;
}

export interface RunSummary {
  id: string;
  factorId: string;
  factorName: string;
  engine: string;
  universe: number;
  days: number;
  createdAt: number;
  status: string;
  elapsedMs: number;
  metrics: RunMetrics;
}

export interface RunDetailData extends RunSummary {
  nav: Array<{ ts: number; nav: number }>;
  trace: Array<{ ts: number; span: string; detail: string }>;
}

export interface HealthData {
  status: string;
  ollamaActive?: boolean;
  llmProvider?: "groq" | "ollama" | "none";
  engines: Array<{ name: string; kind: string; running: boolean; activeRuns: number; lastSharpe: number; sharedImplementation?: boolean }>;
  loaders: Array<{ name: string; online: boolean; wired: boolean }>;
  universe: string[];
  dataSources: Record<string, string>;
  zooLiveCounts: Record<string, number>;
  zooPlannedCounts: Record<string, number>;
  meanIC: number;
  lastBenchedAt: number;
  portfolio: {
    alphaYieldPct: number;
    sharpe: number;
    maxDrawdownPct: number;
    meanIC: number;
    vibeScore: number;
    sourceRunId: string | null;
  };
}

export interface ScanResult {
  ts: number;
  target: string;
  check: SentinelCheck;
  verdict: SentinelVerdict;
  detail: string;
}

export interface LiveQuote {
  name: string;
  price: number;
  open: number;
  prevClose: number;
  high?: number;
  low?: number;
  source: "sina" | "tencent";
  ts: number;
}

export const api = {
  health: () => j<HealthData>("/api/health"),
  alphaList: () => j<AlphaFactor[]>("/api/alpha/list"),
  alpha: (id: string) => j<AlphaFactor>(`/api/alpha/${id}`),
  rebench: () => j<{ factors: number; elapsedMs: number; meanIC: number }>("/api/alpha/bench", { method: "POST" }),
  runs: () => j<RunSummary[]>("/api/runs"),
  run: (id: string) => j<RunDetailData>(`/api/runs/${id}`),
  backtest: (factorId: string, engine = "cross_market", days = 250) =>
    j<RunDetailData>("/api/backtest", { method: "POST", body: JSON.stringify({ factorId, engine, days }) }),
  sentinelScan: (target: string, code: string) =>
    j<ScanResult[]>("/api/sentinel/scan", { method: "POST", body: JSON.stringify({ target, code }) }),
  liveQuotes: () => j<Record<string, LiveQuote>>("/api/quotes/live"),
};

/** POST /api/agent/chat and stream the plaintext token reply. */
export async function chatStream(
  message: string,
  onToken: (chunk: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${BASE}/api/agent/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`chat → ${res.status}`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    onToken(decoder.decode(value, { stream: true }));
  }
}
