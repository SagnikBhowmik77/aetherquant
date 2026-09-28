/* Live SSE client against the FastAPI /api/events stream.
 *
 * On startup we probe /api/health: if the backend answers, seed the store
 * from REST (alphas, engines, sessions) and subscribe to the EventSource;
 * if not, fall back to the in-browser mock engine so the UI always runs.
 */

import { useAetherStore } from "../stores/store";
import type { AgentSession, LogEvent, SentinelScan } from "../types";
import { api } from "./api";
import { startMockStream, stopMockStream } from "./mockStream";

let es: EventSource | null = null;
// generation token instead of a boolean: startStream awaits a probe, so a
// StrictMode mount→cleanup→mount cycle can interleave two calls — any await
// that resumes under a stale generation must abort instead of double-wiring
let generation = 0;

// generous timeout: /api/health does real work (engine fleet, vibe proxy,
// a rate-limited Ollama reachability ping) and during a cold page load the
// dev server's module requests can queue ahead of this fetch — a short
// timeout here wrongly latched the app into mock mode with a live backend
async function probeBackend(timeoutMs = 8000): Promise<boolean> {
  try {
    const ctl = new AbortController();
    const t = window.setTimeout(() => ctl.abort(), timeoutMs);
    const res = await fetch("/api/health", { signal: ctl.signal });
    window.clearTimeout(t);
    return res.ok;
  } catch {
    return false;
  }
}

async function seedFromRest(): Promise<void> {
  const st = useAetherStore.getState();
  const [health, alphas, sessions] = await Promise.all([
    api.health(),
    api.alphaList(),
    fetch("/api/swarm/sessions").then((r) => r.json() as Promise<AgentSession[]>),
  ]);
  st.setAlphas(alphas);
  st.setZooCounts(health.zooLiveCounts, health.zooPlannedCounts, health.lastBenchedAt);
  st.setEngines(health.engines as never);
  st.tickHealth({ loadersOnline: health.loaders.filter((l) => l.online).length });
  // every field in health.portfolio is a real computed number from the
  // backend (best backtest's metrics + the real momentum/volume vibe proxy)
  // — no hardcoded placeholders here anymore.
  st.setMetrics(health.portfolio);
  sessions.forEach((s) => st.upsertSession(s));
}

function wire(source: EventSource): void {
  const st = () => useAetherStore.getState();

  source.addEventListener("log", (e) => {
    const d = JSON.parse((e as MessageEvent).data) as Omit<LogEvent, "id">;
    st().pushLog(d);
  });
  source.addEventListener("alpha", (e) => {
    const d = JSON.parse((e as MessageEvent).data) as { id: string; ic: number };
    st().tickAlpha(d.id, d.ic);
  });
  source.addEventListener("scan", (e) => {
    const d = JSON.parse((e as MessageEvent).data) as Omit<SentinelScan, "id">;
    st().pushScan(d);
  });
  source.addEventListener("equity", (e) => {
    const d = JSON.parse((e as MessageEvent).data) as { ts: number; nav: number };
    st().pushEquity(d);
  });
  source.addEventListener("health", (e) => {
    st().tickHealth(JSON.parse((e as MessageEvent).data));
  });
  source.addEventListener("metrics", (e) => {
    st().setMetrics(JSON.parse((e as MessageEvent).data));
  });
  source.addEventListener("swarm", (e) => {
    st().upsertSession(JSON.parse((e as MessageEvent).data) as AgentSession);
  });

  source.onopen = () => {
    st().setConnected(true);
    st().setDataSource("live");
  };
  source.onerror = () => {
    // EventSource retries automatically; mark degraded but keep it alive
    st().setConnected(false);
  };
}

export async function startStream(): Promise<void> {
  const gen = ++generation;
  const st = useAetherStore.getState();
  st.setDataSource("connecting");

  const alive = await probeBackend();
  if (gen !== generation) return; // superseded by a newer start/stop

  if (alive) {
    stopMockStream();
    try {
      await seedFromRest();
    } catch (err) {
      console.warn("[aetherquant] REST seed failed, continuing with SSE only", err);
    }
    if (gen !== generation) return;
    es = new EventSource("/api/events");
    wire(es);
    st.pushLog({
      ts: Date.now(), level: "info", source: "sse",
      message: "connected to live FastAPI backend — /api/events subscribed",
    });
  } else {
    st.setDataSource("mock");
    st.pushLog({
      ts: Date.now(), level: "warn", source: "sse",
      message: "backend unreachable on /api — running on in-browser mock telemetry",
    });
    startMockStream();
  }
}

export function stopStream(): void {
  generation++;
  es?.close();
  es = null;
  stopMockStream();
  useAetherStore.getState().setConnected(false);
}
