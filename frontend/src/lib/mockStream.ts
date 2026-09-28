/* ────────────────────────────────────────────────────────────
 * Mock SSE engine — dev-mode stand-in for the FastAPI /events
 * stream. Emits the same event shapes the real backend pushes:
 * swarm DAG transitions, execution-loop logs, IC ticks,
 * sentinel verdicts, equity marks, and health telemetry.
 *
 * Swap for lib/sseClient.ts (EventSource against VITE_API_BASE)
 * in production — the store contract is identical.
 * ──────────────────────────────────────────────────────────── */

import { useAetherStore } from "../stores/store";
import type { AgentSession, AlphaFactor, EngineStatus, LogLevel } from "../types";

const rnd = (lo: number, hi: number) => lo + Math.random() * (hi - lo);
const pick = <T,>(xs: readonly T[]): T => xs[Math.floor(Math.random() * xs.length)];

/* ── seed data ─────────────────────────────────────────────── */

const SESSION: AgentSession = {
  id: "swarm-7f3a",
  title: "CN A-share momentum sweep",
  swarmPreset: "(simulated demo — no real preset file)",
  simulated: true,
  startedAt: Date.now() - 1000 * 60 * 14,
  status: "live",
  nodes: [
    { id: "orch", role: "orchestrator", label: "ORCHESTRATOR", status: "running", activity: "routing DAG stage 3/5", tokensUsed: 48210, toolCalls: 31 },
    { id: "scrape", role: "data-scraper", label: "DATA-SCRAPER", status: "streaming", activity: "polling loader chain (see Settings)", tokensUsed: 12040, toolCalls: 12 },
    { id: "vibe", role: "sentiment-scout", label: "VIBE-SCOUT", status: "running", activity: "recomputing momentum/volume proxy", tokensUsed: 9930, toolCalls: 8 },
    { id: "quant", role: "math-quant", label: "MATH-QUANT", status: "running", activity: "ts_rank(delta(vwap,3),9)", tokensUsed: 30125, toolCalls: 22 },
    { id: "risk", role: "risk-manager", label: "RISK-MGR", status: "blocked", activity: "awaiting sentinel verdict", tokensUsed: 5210, toolCalls: 4 },
    { id: "exec", role: "executor", label: "EXECUTOR", status: "idle", activity: "standby — paper mode", tokensUsed: 0, toolCalls: 0 },
  ],
  edges: [
    { from: "orch", to: "scrape", active: true },
    { from: "orch", to: "vibe", active: false },
    { from: "scrape", to: "quant", active: true },
    { from: "vibe", to: "quant", active: false },
    { from: "quant", to: "risk", active: false },
    { from: "risk", to: "exec", active: false },
  ],
};

const ENGINES: EngineStatus[] = [
  { name: "spot_basic", kind: "spot", running: true, activeRuns: 2, lastSharpe: 1.84 },
  { name: "cross_market", kind: "composite", running: true, activeRuns: 1, lastSharpe: 2.11 },
  { name: "options_portfolio", kind: "options", running: true, activeRuns: 1, lastSharpe: 1.42 },
  { name: "multi_asset", kind: "multi-asset", running: false, activeRuns: 0, lastSharpe: 1.67 },
  { name: "derivatives_perp", kind: "derivatives", running: true, activeRuns: 3, lastSharpe: 1.05 },
];

const ALPHA_SEEDS: Array<[string, string, AlphaFactor["zoo"], string]> = [
  ["a101_042", "Alpha#042", "alpha101", "rank(vwap - close) / rank(vwap + close)"],
  ["q158_kmid", "KMID", "qlib158", "(close - open) / open"],
  ["gtja_191_009", "GTJA#009", "gtja191", "sma(((high+low)/2 - (delay(high,1)+delay(low,1))/2) * (high-low)/volume, 7, 2)"],
  ["acad_pead", "PEAD drift", "academic", "decay_linear(earnings_surprise, 12)"],
  ["a101_101", "Alpha#101", "alpha101", "(close - open) / ((high - low) + .001)"],
  ["q158_roc60", "ROC60", "qlib158", "ref(close, 60) / close"],
  ["vibe_momo_7", "VibeMomo-7", "vibe", "ts_rank(vibe_score, 7) * safe_div(volume, adv20)"],
  ["gtja_191_130", "GTJA#130", "gtja191", "rank(decay_linear(corr(high+low/2, mean(volume,40), 9), 10))"],
];

const LOG_SCRIPT: Array<[LogLevel, string, string]> = [
  ["think", "math-quant", "IC on vibe_momo_7 holding at +0.041 over 12d window — promoting to bench cohort"],
  ["tool", "loop.py", "batch_read(3 files) + batch_write(1) — compression layer 4 engaged, saved 18.2k tokens"],
  ["info", "swarm", "edge quant→risk: passing factor tensor (456×2048) via shared discovery bus"],
  ["sentinel", "sentinel", "pre-flight scan alpha_zoo/vibe_momo_7.py — look-ahead-bias: PASS"],
  ["tool", "backtest_tool", "spawned run #8842 on cross_market engine — universe csi300, 2019→2026"],
  ["alpha", "bench_runner", "cohort sweep done: 12 alive / 3 reversed / 1 dead — decay λ=0.94"],
  ["info", "loaders", "duckdb cache hit — symbols served without refetch, see Settings for per-loader status"],
  ["think", "risk-manager", "MVO weights breach single-name cap 8.2% > 8.0% — clamping and re-solving"],
  ["sentinel", "sentinel", "dry-run sandbox: skill patch options_greeks.py — heap delta +0.3MB, no leak"],
  ["info", "loaders", "8 loaders wired (yfinance, binance, coingecko, ccxt, sina, tencent, duckdb-cache, binance-funding) — all real, see Settings"],
  ["info", "vibe-scout", "vibe proxy recomputed from live OHLCV — momentum×volume-z, tanh-squashed to [-1,1]"],
  ["think", "orchestrator", "stage 3 complete — fanning out bench sweep across 4 micro-agents"],
  ["alpha", "bench_runner", "gtja_191_009 IC decayed to 0.006 — flagged for retirement review"],
  ["error", "executor", "paper order rejected: lot size 173 not multiple of 100 — resubmitting 200"],
  ["sentinel", "sentinel", "capital-leakage scan run_8839.py: unbounded retry loop at L142 — BLOCK"],
  ["info", "trace.py", "trace 8842 flushed — 214 spans, 31 tool calls, replay at /runs/8842/trace"],
];
// session_search / skill_writer / remember_tool / web_search flavor-text
// lines were removed — see agent/src/stream.py's LOG_SCRIPT comment for why.

const SCAN_SCRIPT = [
  { target: "alpha_zoo/vibe_momo_7.py", check: "look-ahead-bias", verdict: "pass", detail: "no future-index access in ts_* windows" },
  { target: "skills/options_greeks.py", check: "execution-fault", verdict: "pass", detail: "dry-run clean — heap Δ +0.3MB" },
  { target: "runs/run_8839.py", check: "capital-leakage", verdict: "block", detail: "unbounded order retry loop @ L142" },
  { target: "alpha_zoo/gap_rev_3.py", check: "look-ahead-bias", verdict: "flag", detail: "ref(close,-1) suspicious negative shift" },
  { target: "skills/kelly_sizer.py", check: "capital-leakage", verdict: "pass", detail: "all API errors handled, kill-switch present" },
] as const;

/* ── engine ────────────────────────────────────────────────── */

let started = false;
const timers: number[] = [];

export function startMockStream(): () => void {
  if (started) return stopMockStream;
  started = true;

  const st = useAetherStore.getState();

  // seed
  st.setConnected(true);
  st.upsertSession(SESSION);
  st.setEngines(ENGINES);
  st.setAlphas(
    ALPHA_SEEDS.map(([id, name, zoo, expression]) => {
      const base = rnd(-0.02, 0.06);
      return {
        id,
        name,
        zoo,
        expression,
        ic: base,
        icir: base / 0.11,
        lifecycle: base > 0.015 ? "alive" : base < -0.015 ? "reversed" : "dead",
        icHistory: Array.from({ length: 32 }, (_, i) => base + Math.sin(i / 5) * 0.012 + rnd(-0.008, 0.008)),
        sentinelPassed: id !== "gap_rev_3",
      };
    }),
  );
  st.setMetrics({ alphaYieldPct: 23.7, sharpe: 2.04, maxDrawdownPct: -6.8, meanIC: 0.034, vibeScore: 0.41 });

  let scriptIdx = 0;
  let scanIdx = 0;
  let nav = 1.0;
  let uptime = 14 * 60;

  // rolling execution log — the heartbeat of the terminal
  timers.push(
    window.setInterval(() => {
      const [level, source, message] = LOG_SCRIPT[scriptIdx % LOG_SCRIPT.length];
      scriptIdx++;
      useAetherStore.getState().pushLog({ ts: Date.now(), level, source, message });
    }, 1400),
  );

  // IC ticks on random alphas
  timers.push(
    window.setInterval(() => {
      const s = useAetherStore.getState();
      const a = pick(s.alphas);
      if (a) s.tickAlpha(a.id, a.ic + rnd(-0.006, 0.006));
      s.setMetrics({
        meanIC: s.alphas.reduce((acc, x) => acc + x.ic, 0) / Math.max(1, s.alphas.length),
        vibeScore: Math.max(-1, Math.min(1, s.metrics.vibeScore + rnd(-0.04, 0.045))),
      });
    }, 2200),
  );

  // sentinel scan feed
  timers.push(
    window.setInterval(() => {
      const scan = SCAN_SCRIPT[scanIdx % SCAN_SCRIPT.length];
      scanIdx++;
      useAetherStore.getState().pushScan({ ts: Date.now(), ...scan });
    }, 6500),
  );

  // equity curve — drifting GBM with mild vol
  timers.push(
    window.setInterval(() => {
      nav *= 1 + rnd(-0.0016, 0.0022);
      const s = useAetherStore.getState();
      s.pushEquity({ ts: Date.now(), nav });
      s.setMetrics({
        alphaYieldPct: (nav - 1) * 100 * 8 + 23.7,
        sharpe: 2.04 + (nav - 1) * 6,
      });
    }, 1800),
  );

  // health telemetry
  timers.push(
    window.setInterval(() => {
      uptime += 2;
      useAetherStore.getState().tickHealth({
        cpuPct: Math.round(rnd(31, 74)),
        memPct: Math.round(rnd(42, 61)),
        eventsPerSec: Math.round(rnd(2, 8)),
        ssePipes: 4,
        uptimeSec: uptime,
      });
    }, 2000),
  );

  // swarm DAG choreography — pulse edges + rotate node states
  const EDGE_CYCLE = SESSION.edges.map((e) => [e.from, e.to] as const);
  let edgeIdx = 0;
  timers.push(
    window.setInterval(() => {
      const s = useAetherStore.getState();
      const [pf, pt] = EDGE_CYCLE[edgeIdx % EDGE_CYCLE.length];
      const [nf, nt] = EDGE_CYCLE[(edgeIdx + 1) % EDGE_CYCLE.length];
      s.pulseEdge(SESSION.id, pf, pt, false);
      s.pulseEdge(SESSION.id, nf, nt, true);
      edgeIdx++;

      const node = pick(SESSION.nodes);
      s.bumpNodeCounters(SESSION.id, node.id, Math.round(rnd(80, 900)), Math.random() > 0.6 ? 1 : 0);
      if (node.id === "risk" && Math.random() > 0.5) {
        s.setNodeStatus(SESSION.id, "risk", "running", "re-solving MVO under caps");
      }
    }, 2600),
  );

  return stopMockStream;
}

export function stopMockStream(): void {
  timers.forEach((t) => window.clearInterval(t));
  timers.length = 0;
  started = false;
  useAetherStore.getState().setConnected(false);
}
