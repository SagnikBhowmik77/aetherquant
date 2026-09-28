/* Agent / Swarm Chat — split screen: LLM chat terminal beside the
 * rolling SSE execution log. Chat replies stream from the backend
 * (which can launch REAL backtests mid-conversation). */

import { useEffect, useRef, useState } from "react";
import { chatStream } from "../lib/api";
import { useAetherStore } from "../stores/store";
import { PanelHeader, Terminal } from "../components/Terminal";

interface ChatMsg {
  role: "user" | "assistant";
  text: string;
  streaming?: boolean;
}

const SUGGESTIONS = [
  "show me the top alphas",
  "backtest vibe_momo_7",
  "how is vibe sentiment doing?",
  "explain the sentinel scans",
];

export default function AgentChat() {
  const dataSource = useAetherStore((s) => s.dataSource);
  const session = useAetherStore((s) => s.sessions.find((x) => x.id === s.activeSessionId) ?? s.sessions[0]);
  const [messages, setMessages] = useState<ChatMsg[]>([
    {
      role: "assistant",
      text: "AetherQuant orchestrator online. I can bench the zoo, launch real backtests through the engine fleet, read vibe sentiment, and explain sentinel verdicts. What are we hunting?",
    },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const send = async (text: string) => {
    const msg = text.trim();
    if (!msg || busy) return;
    setInput("");
    setBusy(true);
    setMessages((m) => [...m, { role: "user", text: msg }, { role: "assistant", text: "", streaming: true }]);

    const append = (chunk: string) =>
      setMessages((m) => {
        const next = m.slice();
        const last = next[next.length - 1];
        next[next.length - 1] = { ...last, text: last.text + chunk };
        return next;
      });

    try {
      if (dataSource === "live") {
        await chatStream(msg, append);
      } else {
        // mock fallback — no backend to answer
        const canned =
          "Backend offline — I'm running on mock telemetry, so chat reasoning is unavailable. " +
          "Start the API (`python -m uvicorn api_server:app --app-dir aetherquant/agent --port 8700`) " +
          "and I'll bench alphas and launch real backtests from right here.";
        for (const w of canned.split(" ")) {
          append(w + " ");
          await new Promise((r) => setTimeout(r, 18));
        }
      }
    } catch (e) {
      append(`\n\n[stream error: ${String(e)}]`);
    } finally {
      setMessages((m) => {
        const next = m.slice();
        next[next.length - 1] = { ...next[next.length - 1], streaming: false };
        return next;
      });
      setBusy(false);
    }
  };

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 h-full min-h-[540px]">
      {/* ── chat terminal ── */}
      <section className="aq-glass rounded-lg overflow-hidden flex flex-col min-h-[420px]">
        <PanelHeader
          title="Agent Chat · Orchestrator"
          right={
            session && (
              <span className="text-[10px] font-medium text-slate-400 flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-indigo-400 aq-pulse" />
                <span className="font-mono">{session.id}</span> · {session.nodes.length} stages
              </span>
            )
          }
        />
        <div ref={bodyRef} className="flex-1 min-h-0 overflow-y-auto aq-scroll p-4 space-y-3 text-[11px]">
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[85%] rounded-lg px-3 py-2 leading-relaxed whitespace-pre-wrap break-words ${
                  m.role === "user"
                    ? "bg-indigo-500/10 border border-indigo-400/20 text-slate-200"
                    : "bg-[#111827]/70 border border-slate-700/50 text-slate-300"
                }`}
              >
                {m.role === "assistant" && (
                  <span className="block text-[9px] font-semibold uppercase tracking-[0.08em] text-emerald-400/90 mb-1">
                    Orchestrator
                  </span>
                )}
                {m.text}
                {m.streaming && <span className="aq-caret text-emerald-400">▊</span>}
              </div>
            </div>
          ))}
        </div>
        <div className="border-t border-slate-700/40 p-3 space-y-2">
          <div className="flex gap-1.5 flex-wrap">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => send(s)}
                disabled={busy}
                className="text-[9.5px] font-medium px-2 py-1 rounded border border-slate-700/60 text-slate-500 hover:text-slate-300 hover:border-slate-600 transition-colors disabled:opacity-40"
              >
                {s}
              </button>
            ))}
          </div>
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              void send(input);
            }}
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={busy ? "orchestrator is thinking…" : "ask the swarm anything…"}
              disabled={busy}
              className="flex-1 bg-[#0a0e14] border border-slate-700/60 rounded-lg px-3 py-2 text-[11.5px] text-slate-200 placeholder:text-slate-600 outline-none focus:border-indigo-400/50 disabled:opacity-60"
            />
            <button
              type="submit"
              disabled={busy || !input.trim()}
              className="px-4 rounded-lg bg-indigo-500/90 text-white text-[11px] font-semibold hover:bg-indigo-500 transition-colors disabled:opacity-40"
            >
              Send
            </button>
          </form>
        </div>
      </section>

      {/* ── live execution log ── */}
      <div className="flex min-h-[420px]">
        <Terminal title="Swarm Execution · live SSE" />
      </div>
    </div>
  );
}
