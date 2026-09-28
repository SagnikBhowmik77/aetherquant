/* ────────────────────────────────────────────────────────────
 * AetherQuant — shared domain types
 * Mirrors the FastAPI backend schemas (agent/src/api/).
 * ──────────────────────────────────────────────────────────── */

export type LogLevel = "info" | "tool" | "think" | "warn" | "error" | "sentinel" | "alpha";

/** One event on the real-time SSE execution stream. */
export interface LogEvent {
  id: number;
  ts: number; // epoch ms
  level: LogLevel;
  /** emitting agent / subsystem, e.g. "math-quant", "sentinel", "loop.py" */
  source: string;
  message: string;
}

export type AgentRole =
  | "orchestrator"
  | "data-scraper"
  | "math-quant"
  | "risk-manager"
  | "sentiment-scout"
  | "executor";

export type NodeStatus = "idle" | "running" | "streaming" | "blocked" | "done" | "failed";

/** A stage in the live pipeline DAG. With the backend live these are REAL
 * counters: tokensUsed only increments with genuine Ollama token counts
 * from actual chat calls, toolCalls/activity only change when the
 * corresponding backend subsystem does real work (see agent/src/stream.py
 * node_event). Only the offline mock fallback fabricates them — flagged
 * via AgentSession.simulated. */
export interface SwarmNode {
  id: string;
  role: AgentRole;
  label: string;
  status: NodeStatus;
  /** short description of current activity, shown under the node */
  activity: string;
  tokensUsed: number;
  toolCalls: number;
}

export interface SwarmEdge {
  from: string;
  to: string;
  /** true while a data token is actively flowing across this edge */
  active: boolean;
}

export interface AgentSession {
  id: string;
  title: string;
  swarmPreset: string;
  startedAt: number;
  status: "live" | "paused" | "completed";
  nodes: SwarmNode[];
  edges: SwarmEdge[];
  /** true only for the offline in-browser mock fallback; the live backend
   * always sends false — its DAG state is real pipeline telemetry */
  simulated?: boolean;
}

export type AlphaZooOrigin = "qlib158" | "alpha101" | "gtja191" | "academic" | "vibe";
export type AlphaLifecycle = "alive" | "reversed" | "dead";

/** A factor from the alpha zoo — only the ones with real code are ever
 * present here (see store.zooLiveCounts vs zooPlannedCounts). */
export interface AlphaFactor {
  id: string;
  name: string;
  zoo: AlphaZooOrigin;
  expression: string;
  ic: number; // real spearman IC, refreshed on a real periodic re-bench — never jittered
  icir: number;
  lifecycle: AlphaLifecycle;
  /** rolling IC history for decay sparklines (most recent last) */
  icHistory: number[];
  sentinelPassed: boolean;
}

export type SentinelCheck = "look-ahead-bias" | "capital-leakage" | "execution-fault";
export type SentinelVerdict = "pass" | "flag" | "block";

/** Result of the adversarial pre-flight scan on agent-written code. */
export interface SentinelScan {
  id: number;
  ts: number;
  target: string; // e.g. "alpha_zoo/vibe_momo_7.py"
  check: SentinelCheck;
  verdict: SentinelVerdict;
  detail: string;
}

export interface EngineStatus {
  name: string;
  kind: "spot" | "multi-asset" | "derivatives" | "options" | "composite";
  running: boolean;
  activeRuns: number;
  lastSharpe: number;
  /** true = all 5 engines currently share one real backtest implementation;
   * "kind" doesn't yet imply distinct pricing/risk math */
  sharedImplementation?: boolean;
}

export interface SystemHealth {
  cpuPct: number; // real psutil system CPU utilization
  memPct: number; // real psutil system memory utilization
  eventsPerSec: number; // real count of SSE events published by the hub
  ssePipes: number;
  loadersOnline: number;
  uptimeSec: number;
  nextRebenchInSec?: number;
}

/** One mark on the aggregate strategy equity curve. */
export interface EquityMark {
  ts: number;
  nav: number; // normalized to 1.0 at session start
}

export interface PortfolioMetrics {
  alphaYieldPct: number; // annualized excess return
  sharpe: number;
  maxDrawdownPct: number;
  meanIC: number;
  vibeScore: number; // -1..1 aggregate sentiment momentum
}
