/* Interactive DAG Canvas — full-viewport swarm workflow visualizer.
 * Nodes are live store state; data tokens animate along active edges. */

import { useState } from "react";
import { useAetherStore } from "../stores/store";
import type { NodeStatus, SwarmNode } from "../types";
import { PanelHeader } from "../components/Terminal";

/* layout in a 1000×420 design space, rendered as % positions */
const POS: Record<string, { x: number; y: number }> = {
  orch: { x: 8, y: 50 },
  scrape: { x: 30, y: 22 },
  vibe: { x: 30, y: 78 },
  quant: { x: 54, y: 50 },
  risk: { x: 74, y: 50 },
  exec: { x: 92, y: 50 },
};

const STATUS_RING: Record<NodeStatus, string> = {
  idle: "border-slate-700",
  running: "border-indigo-400/60",
  streaming: "border-cyan-400/50",
  blocked: "border-amber-500/50",
  done: "border-emerald-500/50",
  failed: "border-rose-500/60",
};

const STATUS_TEXT: Record<NodeStatus, string> = {
  idle: "text-slate-500",
  running: "text-indigo-300",
  streaming: "text-cyan-300",
  blocked: "text-amber-300",
  done: "text-emerald-300",
  failed: "text-rose-400",
};

const ROLE_ICON: Record<string, string> = {
  orchestrator: "⌬",
  "data-scraper": "⇣",
  "sentiment-scout": "☄",
  "math-quant": "∑",
  "risk-manager": "⛨",
  executor: "▶",
};

function edgePath(from: string, to: string): string {
  const a = POS[from];
  const b = POS[to];
  if (!a || !b) return "";
  const mx = (a.x + b.x) / 2;
  return `M ${a.x} ${a.y} C ${mx} ${a.y}, ${mx} ${b.y}, ${b.x} ${b.y}`;
}

const fmtK = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n));

export default function DagCanvas() {
  const session = useAetherStore((s) => s.sessions.find((x) => x.id === s.activeSessionId) ?? s.sessions[0]);
  const [focusId, setFocusId] = useState<string | null>(null);

  if (!session) {
    return (
      <section className="aq-glass rounded-lg p-10 text-center text-slate-600 text-[11px]">
        no live swarm session — waiting for stream…
      </section>
    );
  }

  const focus: SwarmNode | undefined = session.nodes.find((n) => n.id === focusId);

  return (
    <div className="flex flex-col gap-4 h-full">
      <section className="aq-glass rounded-lg overflow-hidden flex-1 flex flex-col min-h-[480px]">
        <PanelHeader
          title={`Swarm DAG · ${session.id}`}
          right={
            <div className="flex items-center gap-2">
              {session.simulated && (
                <span
                  className="text-[8px] font-semibold tracking-wide px-1.5 py-0.5 rounded border border-amber-500/30 text-amber-400/90 bg-amber-500/5"
                  title="offline mock session — backend unreachable, so this DAG is placeholder data. With the backend live, every counter here is real pipeline telemetry and this badge disappears."
                >
                  SIMULATED
                </span>
              )}
              <span className="text-[10px] font-medium text-slate-400 flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-indigo-400 aq-pulse" />
                {session.title}
              </span>
            </div>
          }
        />
        <div className="relative flex-1 min-h-0 m-3 rounded-lg bg-[#0a0e14] border border-slate-800/60 overflow-hidden">
          {/* edges + animated data tokens */}
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 w-full h-full">
            {session.edges.map((e) => {
              const d = edgePath(e.from, e.to);
              return (
                <g key={`${e.from}-${e.to}`}>
                  <path
                    d={d}
                    fill="none"
                    stroke={e.active ? "#818cf8" : "#334155"}
                    strokeOpacity={e.active ? 0.85 : 0.5}
                    strokeWidth={e.active ? 0.45 : 0.3}
                    strokeDasharray={e.active ? "none" : "1.4 1.4"}
                    vectorEffect="non-scaling-stroke"
                  />
                  {e.active && (
                    <circle r="0.7" fill="#818cf8">
                      <animateMotion dur="1.6s" repeatCount="indefinite" path={d} />
                    </circle>
                  )}
                </g>
              );
            })}
          </svg>

          {/* nodes */}
          {session.nodes.map((n) => {
            const p = POS[n.id] ?? { x: 50, y: 50 };
            return (
              <button
                key={n.id}
                onClick={() => setFocusId(n.id === focusId ? null : n.id)}
                style={{ left: `${p.x}%`, top: `${p.y}%` }}
                className={`absolute -translate-x-1/2 -translate-y-1/2 rounded-md border bg-[#111827] px-3 py-2 text-left transition-all w-[138px] ${STATUS_RING[n.status]} ${
                  focusId === n.id ? "scale-105 z-10" : "hover:border-slate-500"
                }`}
              >
                <div className="flex items-center gap-1.5">
                  <span className={`text-sm ${STATUS_TEXT[n.status]}`}>{ROLE_ICON[n.role] ?? "⬡"}</span>
                  <span className={`text-[9px] font-semibold tracking-wide ${STATUS_TEXT[n.status]}`}>{n.label}</span>
                </div>
                <p className="mt-1 text-[9px] text-slate-500 leading-tight truncate">{n.activity}</p>
                <p className="mt-0.5 text-[8px] text-slate-600 tabular-nums font-mono uppercase">
                  {n.status} · {fmtK(n.tokensUsed)} tok
                </p>
              </button>
            );
          })}
        </div>
      </section>

      {/* focus inspector */}
      {focus && (
        <section className="aq-glass rounded-lg overflow-hidden">
          <PanelHeader
            title={`Inspector · ${focus.label}`}
            right={
              <button onClick={() => setFocusId(null)} className="text-slate-500 hover:text-slate-300 text-xs px-1">
                ✕
              </button>
            }
          />
          <div className="p-4 grid grid-cols-2 sm:grid-cols-4 gap-4 text-[11px]">
            <div>
              <p className="text-[9px] uppercase tracking-wider text-slate-600">Role</p>
              <p className="text-slate-200 font-semibold">{focus.role}</p>
            </div>
            <div>
              <p className="text-[9px] uppercase tracking-wider text-slate-600">Status</p>
              <p className={`font-semibold uppercase ${STATUS_TEXT[focus.status]}`}>{focus.status}</p>
            </div>
            <div>
              <p className="text-[9px] uppercase tracking-wider text-slate-600">Tokens Used</p>
              <p className="text-slate-200 font-semibold font-mono tabular-nums">{focus.tokensUsed.toLocaleString()}</p>
            </div>
            <div>
              <p className="text-[9px] uppercase tracking-wider text-slate-600">Tool Calls</p>
              <p className="text-slate-200 font-semibold font-mono tabular-nums">{focus.toolCalls}</p>
            </div>
            <div className="col-span-2 sm:col-span-4">
              <p className="text-[9px] uppercase tracking-wider text-slate-600">Current Activity</p>
              <p className="text-slate-300">{focus.activity}</p>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
