/* ────────────────────────────────────────────────────────────
 * AetherQuant — global state (Zustand)
 *
 * Single source of truth for:
 *   • active agent/swarm sessions and their live DAG state
 *   • the real-time SSE log queue (bounded ring buffer)
 *   • Alpha Zoo metrics + IC decay histories
 *   • sentinel (adversarial pre-flight) scan feed
 *   • engine fleet + system health telemetry
 *   • aggregate equity curve + portfolio metrics
 *
 * All mutations flow through actions so the SSE client
 * (lib/sseClient.ts | lib/mockStream.ts) stays render-agnostic.
 * ──────────────────────────────────────────────────────────── */

import { create } from "zustand";
import type {
  AgentSession,
  AlphaFactor,
  EngineStatus,
  EquityMark,
  LogEvent,
  NodeStatus,
  PortfolioMetrics,
  SentinelScan,
  SystemHealth,
} from "../types";

const LOG_BUFFER_CAP = 400;
const SCAN_BUFFER_CAP = 60;
const EQUITY_CAP = 240;
const IC_HISTORY_CAP = 48;

export type DataSource = "connecting" | "live" | "mock";

interface AetherState {
  /* ── connection ── */
  connected: boolean;
  dataSource: DataSource;
  streamStartedAt: number;

  /* ── agent sessions / swarms ── */
  sessions: AgentSession[];
  activeSessionId: string | null;

  /* ── real-time log queue ── */
  logs: LogEvent[];
  logsPaused: boolean;

  /* ── alpha zoo ── */
  alphas: AlphaFactor[];
  /** real per-zoo counts of factors that actually have code (== alphas.length) */
  zooLiveCounts: Record<string, number>;
  /** target roster from the architecture spec — NOT implemented, kept
   * separate so the UI can never imply these are live */
  zooPlannedCounts: Record<string, number>;
  /** epoch ms of the last real bench_all() recompute; 0 = not yet known */
  lastBenchedAt: number;

  /* ── sentinel sandbox feed ── */
  scans: SentinelScan[];

  /* ── engines + telemetry ── */
  engines: EngineStatus[];
  health: SystemHealth;

  /* ── portfolio ── */
  equity: EquityMark[];
  metrics: PortfolioMetrics;

  /* ── actions ── */
  setConnected: (connected: boolean) => void;
  setDataSource: (dataSource: DataSource) => void;
  pushLog: (e: Omit<LogEvent, "id">) => void;
  toggleLogsPaused: () => void;
  upsertSession: (s: AgentSession) => void;
  setActiveSession: (id: string | null) => void;
  setNodeStatus: (sessionId: string, nodeId: string, status: NodeStatus, activity?: string) => void;
  pulseEdge: (sessionId: string, from: string, to: string, active: boolean) => void;
  bumpNodeCounters: (sessionId: string, nodeId: string, tokens: number, toolCalls: number) => void;
  setAlphas: (alphas: AlphaFactor[]) => void;
  setZooCounts: (zooLiveCounts: Record<string, number>, zooPlannedCounts: Record<string, number>, lastBenchedAt: number) => void;
  tickAlpha: (id: string, ic: number) => void;
  pushScan: (s: Omit<SentinelScan, "id">) => void;
  setEngines: (engines: EngineStatus[]) => void;
  tickHealth: (partial: Partial<SystemHealth>) => void;
  pushEquity: (mark: EquityMark) => void;
  setMetrics: (partial: Partial<PortfolioMetrics>) => void;
}

let logSeq = 0;
let scanSeq = 0;

export const useAetherStore = create<AetherState>()((set) => ({
  connected: false,
  dataSource: "connecting",
  streamStartedAt: Date.now(),

  sessions: [],
  activeSessionId: null,

  logs: [],
  logsPaused: false,

  alphas: [],
  zooLiveCounts: {},
  zooPlannedCounts: {},
  lastBenchedAt: 0,

  scans: [],

  engines: [],
  health: {
    cpuPct: 0,
    memPct: 0,
    eventsPerSec: 0,
    ssePipes: 0,
    loadersOnline: 0,
    uptimeSec: 0,
  },

  equity: [{ ts: Date.now(), nav: 1 }],
  metrics: {
    alphaYieldPct: 0,
    sharpe: 0,
    maxDrawdownPct: 0,
    meanIC: 0,
    vibeScore: 0,
  },

  setConnected: (connected) => set({ connected }),

  setDataSource: (dataSource) => set({ dataSource }),

  pushLog: (e) =>
    set((st) => {
      if (st.logsPaused) return st;
      const next = st.logs.length >= LOG_BUFFER_CAP ? st.logs.slice(-LOG_BUFFER_CAP + 1) : st.logs.slice();
      next.push({ ...e, id: ++logSeq });
      return { logs: next };
    }),

  toggleLogsPaused: () => set((st) => ({ logsPaused: !st.logsPaused })),

  upsertSession: (s) =>
    set((st) => {
      const idx = st.sessions.findIndex((x) => x.id === s.id);
      const sessions = st.sessions.slice();
      if (idx >= 0) sessions[idx] = s;
      else sessions.push(s);
      return { sessions, activeSessionId: st.activeSessionId ?? s.id };
    }),

  setActiveSession: (id) => set({ activeSessionId: id }),

  setNodeStatus: (sessionId, nodeId, status, activity) =>
    set((st) => ({
      sessions: st.sessions.map((s) =>
        s.id !== sessionId
          ? s
          : {
              ...s,
              nodes: s.nodes.map((n) =>
                n.id !== nodeId ? n : { ...n, status, activity: activity ?? n.activity },
              ),
            },
      ),
    })),

  pulseEdge: (sessionId, from, to, active) =>
    set((st) => ({
      sessions: st.sessions.map((s) =>
        s.id !== sessionId
          ? s
          : {
              ...s,
              edges: s.edges.map((e) =>
                e.from === from && e.to === to ? { ...e, active } : e,
              ),
            },
      ),
    })),

  bumpNodeCounters: (sessionId, nodeId, tokens, toolCalls) =>
    set((st) => ({
      sessions: st.sessions.map((s) =>
        s.id !== sessionId
          ? s
          : {
              ...s,
              nodes: s.nodes.map((n) =>
                n.id !== nodeId
                  ? n
                  : { ...n, tokensUsed: n.tokensUsed + tokens, toolCalls: n.toolCalls + toolCalls },
              ),
            },
      ),
    })),

  setAlphas: (alphas) => set({ alphas }),

  setZooCounts: (zooLiveCounts, zooPlannedCounts, lastBenchedAt) =>
    set({ zooLiveCounts, zooPlannedCounts, lastBenchedAt }),

  tickAlpha: (id, ic) =>
    set((st) => ({
      alphas: st.alphas.map((a) => {
        if (a.id !== id) return a;
        const icHistory = [...a.icHistory.slice(-IC_HISTORY_CAP + 1), ic];
        const lifecycle = ic > 0.015 ? "alive" : ic < -0.015 ? "reversed" : a.lifecycle;
        return { ...a, ic, icHistory, lifecycle };
      }),
    })),

  pushScan: (s) =>
    set((st) => {
      const next = st.scans.length >= SCAN_BUFFER_CAP ? st.scans.slice(-SCAN_BUFFER_CAP + 1) : st.scans.slice();
      next.push({ ...s, id: ++scanSeq });
      return { scans: next };
    }),

  setEngines: (engines) => set({ engines }),

  tickHealth: (partial) => set((st) => ({ health: { ...st.health, ...partial } })),

  pushEquity: (mark) =>
    set((st) => {
      const equity =
        st.equity.length >= EQUITY_CAP ? st.equity.slice(-EQUITY_CAP + 1) : st.equity.slice();
      equity.push(mark);
      return { equity };
    }),

  setMetrics: (partial) => set((st) => ({ metrics: { ...st.metrics, ...partial } })),
}));

/* ── derived selectors ─────────────────────────────────────── */

export const selectActiveSession = (st: AetherState): AgentSession | undefined =>
  st.sessions.find((s) => s.id === st.activeSessionId) ?? st.sessions[0];

export const selectLiveSwarmCount = (st: AetherState): number =>
  st.sessions.filter((s) => s.status === "live").length;

/** Real count of factors with actual code — use this for headline stats,
 * never the planned/target roster. */
export const selectZooLiveTotal = (st: AetherState): number => st.alphas.length;

export const selectZooPlannedTotal = (st: AetherState): number =>
  Object.values(st.zooPlannedCounts).reduce((a, b) => a + b, 0);
