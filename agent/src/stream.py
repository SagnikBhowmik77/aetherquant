"""SSE event hub + background telemetry loop.

One asyncio hub fans events out to every connected /api/events client.
The telemetry loop drives the live dashboard: a periodic REAL IC re-bench
(no per-tick jitter), sentinel scans (the REAL scanner over a sample
corpus), a real live paper-trading NAV mark (src/paper/engine.py), real
per-loader reachability probes, real vibe-proxy readings, and real
process/system health via psutil.

Everything here is real: the equity curve is `paper.engine.aggregate_nav()`
— a forward-advancing paper portfolio marked against live/cached prices;
vibeScore is market.aggregate_vibe(); alpha IC values only change when
bench_all() actually reruns; CPU/MEM are real psutil readings;
eventsPerSec is a real count of SSE events published; loader status comes
from genuine per-loader probes.

The pipeline DAG (SESSION) is real telemetry too, not a scripted
choreography: every node's activity/status/toolCalls only changes when
the corresponding real subsystem actually does work (node_event below),
tokensUsed only increments with real Ollama token counts from actual chat
calls, and edges pulse only when real work flows between stages. There is
deliberately no random state machine and no fabricated counters anywhere
in this file.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import time

import psutil

from .backtest.engine import best_run
from .factors.registry import REGISTRY, bench_all, mean_ic
from .market import LOADERS, aggregate_vibe, loader_status, probe_all_loaders, refresh_quotes
from .paper import engine as paper_engine
from .sentinel.scanner import full_scan

# ── hub ────────────────────────────────────────────────────────────


class Hub:
    def __init__(self) -> None:
        self.subscribers: set[asyncio.Queue] = set()
        self.events_published = 0  # real counter — backs the "events/sec" health stat

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self.subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subscribers.discard(q)

    def publish(self, event: str, data: dict) -> None:
        self.events_published += 1
        for q in list(self.subscribers):
            try:
                q.put_nowait((event, data))
            except asyncio.QueueFull:
                self.unsubscribe(q)


hub = Hub()


def log(level: str, source: str, message: str) -> None:
    hub.publish("log", {"ts": int(time.time() * 1000),
                        "level": level, "source": source, "message": message})


# ── real pipeline telemetry DAG ─────────────────────────────────────
# Six stages of the actual system. Counters start at zero and only move
# when the corresponding real subsystem does real work; tokensUsed is
# only ever incremented with genuine Ollama token counts.

SESSION: dict = {
    "id": "pipeline-live",
    "title": "live pipeline telemetry",
    "swarmPreset": "real event stream — every counter increments only on real work",
    "simulated": False,
    "startedAt": int(time.time() * 1000),
    "status": "live",
    "nodes": [
        {"id": "orch",   "role": "orchestrator",    "label": "ORCHESTRATOR", "status": "idle", "activity": "awaiting chat (Ollama tool-calling loop)", "tokensUsed": 0, "toolCalls": 0},
        {"id": "scrape", "role": "data-scraper",    "label": "DATA-SCRAPER", "status": "idle", "activity": "awaiting first loader probe",              "tokensUsed": 0, "toolCalls": 0},
        {"id": "vibe",   "role": "sentiment-scout", "label": "VIBE-SCOUT",   "status": "idle", "activity": "awaiting first vibe recompute",            "tokensUsed": 0, "toolCalls": 0},
        {"id": "quant",  "role": "math-quant",      "label": "MATH-QUANT",   "status": "idle", "activity": "awaiting first re-bench",                  "tokensUsed": 0, "toolCalls": 0},
        {"id": "risk",   "role": "risk-manager",    "label": "RISK-MGR",     "status": "idle", "activity": "awaiting first sentinel scan",             "tokensUsed": 0, "toolCalls": 0},
        {"id": "exec",   "role": "executor",        "label": "EXECUTOR",     "status": "idle", "activity": "awaiting first paper mark",                "tokensUsed": 0, "toolCalls": 0},
    ],
    "edges": [
        {"from": "orch", "to": "scrape", "active": False},
        {"from": "orch", "to": "vibe", "active": False},
        {"from": "scrape", "to": "quant", "active": False},
        {"from": "vibe", "to": "quant", "active": False},
        {"from": "quant", "to": "risk", "active": False},
        {"from": "risk", "to": "exec", "active": False},
    ],
}

# which edge lights up when a given stage does real work (upstream → node)
_EDGE_FOR = {
    "scrape": ("orch", "scrape"),
    "vibe": ("orch", "vibe"),
    "quant": ("scrape", "quant"),
    "risk": ("quant", "risk"),
    "exec": ("risk", "exec"),
}

NODE_IDLE_AFTER_S = 20
EDGE_CLEAR_AFTER_S = 5
_node_last_event: dict[str, float] = {}
_edge_last_pulse: float = 0.0


def node_event(node_id: str, activity: str, tokens: int = 0,
               tool_call: bool = False, status: str = "running") -> None:
    """Record REAL work by a pipeline stage — the only way DAG state moves.
    `tokens` must be a genuine token count (Ollama eval/prompt counts)."""
    global _edge_last_pulse
    for n in SESSION["nodes"]:
        if n["id"] == node_id:
            n["activity"] = activity
            n["tokensUsed"] += max(0, tokens)
            if tool_call:
                n["toolCalls"] += 1
            n["status"] = status
            break
    _node_last_event[node_id] = time.time()
    pair = _EDGE_FOR.get(node_id)
    if pair:
        for e in SESSION["edges"]:
            e["active"] = (e["from"], e["to"]) == pair
        _edge_last_pulse = time.time()
    hub.publish("swarm", SESSION)


def _idle_out() -> None:
    """Return nodes to idle / clear edge pulses once real work stops —
    time-based decay of display state, not invented activity."""
    global _edge_last_pulse
    now = time.time()
    changed = False
    for n in SESSION["nodes"]:
        last = _node_last_event.get(n["id"], 0)
        if n["status"] != "idle" and now - last > NODE_IDLE_AFTER_S:
            n["status"] = "idle"
            changed = True
    if _edge_last_pulse and now - _edge_last_pulse > EDGE_CLEAR_AFTER_S:
        for e in SESSION["edges"]:
            if e["active"]:
                e["active"] = False
                changed = True
        _edge_last_pulse = 0.0
    if changed:
        hub.publish("swarm", SESSION)


# sample snippets fed through the REAL sentinel scanner — the corpus is
# fixed but every scan result is genuinely computed by the AST scanner
SENTINEL_SAMPLES = [
    ("alpha_zoo/vibe_momo_7.py",
     "def signal(close, vibe):\n    return ts_rank(vibe, 7) * safe_div(close, sma(close, 20))\n"),
    ("runs/run_8839_exec.py",
     "def flush(api, order):\n    while True:\n        api.submit_order(order)\n"),
    ("alpha_zoo/gap_rev_3.py",
     "def signal(close):\n    return ref(close, -1) / close - 1\n"),
    ("skills/kelly_sizer.py",
     "def size(edge, odds):\n    if odds <= 0:\n        return 0.0\n    return max(0.0, min(0.5, edge / odds))\n"),
    ("skills/options_greeks.py",
     "def fetch(api):\n    try:\n        return api.chain('510050')\n    except Exception:\n        pass\n"),
]

_uptime = 0  # real seconds since the telemetry loop started — no fake offset
REBENCH_EVERY_S = 300   # real periodic IC recompute — see bench_all() docstring
PROBE_EVERY_S = 300     # real per-loader reachability probes


async def _probe_and_report() -> None:
    results = await asyncio.to_thread(probe_all_loaders)
    n = sum(1 for ok in results.values() if ok)
    live = ", ".join(k for k, ok in results.items() if ok) or "none"
    log("info", "loaders", f"reachability probe: {n}/{len(LOADERS)} loaders live — {live}")
    node_event("scrape", f"probed {len(LOADERS)} loaders — {n} reachable", tool_call=True)
    hub.publish("health", {"loadersOnline": n})


async def telemetry_loop() -> None:
    global _uptime
    scan_idx = 0
    tick = 0

    # psutil needs one throwaway call to establish its internal baseline —
    # the first real reading comes on the next call
    proc = psutil.Process(os.getpid())
    proc.cpu_percent(None)
    psutil.cpu_percent(None)
    last_event_count = hub.events_published
    last_event_ts = time.time()

    # first real loader probe right away (in a thread — probes block)
    asyncio.ensure_future(_probe_and_report())

    while True:
        await asyncio.sleep(1.0)
        tick += 1
        _uptime += 1

        _idle_out()

        # narrate a real factor's current real IC every ~6s — the pick is
        # random but every number shown is the genuine current registry value
        if tick % 6 == 0 and REGISTRY:
            a = random.choice(list(REGISTRY.values()))
            log("alpha", "bench_runner",
                f"{a['name']} IC {a['ic']:+.4f} (ICIR {a['icir']:.2f}) — {a['lifecycle']}, zoo {a['zoo']}")

        # real periodic re-bench — no per-tick jitter. IC only moves when
        # this actually reruns the spearman calc (in a thread: it's CPU-bound)
        if tick % REBENCH_EVERY_S == 0 and REGISTRY:
            await asyncio.to_thread(bench_all)
            for fid, a in REGISTRY.items():
                hub.publish("alpha", {"id": fid, "ic": a["ic"]})
            vibe = aggregate_vibe()
            hub.publish("metrics", {"meanIC": mean_ic(), "vibeScore": vibe})
            log("alpha", "bench_runner", f"real re-bench complete — {len(REGISTRY)} factors recomputed")
            node_event("quant", f"re-benched {len(REGISTRY)} factors — mean IC {mean_ic():+.4f}", tool_call=True)
            node_event("vibe", f"aggregate vibe {vibe:+.3f} off live OHLCV", tool_call=True)

        # refresh the CN live-quote snapshot every ~13s (blocking urllib →
        # thread) — without this the CN legs of paper mark-to-market and
        # /api/quotes/live would go stale forever after boot
        if tick % 13 == 0:
            await asyncio.to_thread(refresh_quotes)
            node_event("scrape", "CN quote snapshot refreshed (sina/tencent)")

        # re-probe loader reachability every 5 min (offset from re-bench)
        if tick % PROBE_EVERY_S == PROBE_EVERY_S // 2:
            asyncio.ensure_future(_probe_and_report())

        # equity mark every 2s — real forward-advancing paper P&L (see
        # src/paper/engine.py; may hit the live crypto ticker → thread)
        if tick % 2 == 1:
            nav = await asyncio.to_thread(paper_engine.aggregate_nav)
            if nav is not None:
                hub.publish("equity", {"ts": int(time.time() * 1000), "nav": round(nav, 6)})
                if tick % 30 == 1:
                    node_event("exec", f"paper NAV marked {nav:.4f} (5 books, live/cached tiers)")
            br = best_run()
            if br:
                hub.publish("metrics", {
                    "alphaYieldPct": br["metrics"]["annRetPct"],
                    "sharpe": br["metrics"]["sharpe"],
                    "maxDrawdownPct": br["metrics"]["maxDrawdownPct"],
                })

        # health every 2s — all real readings (see module docstring)
        if tick % 2 == 0:
            now = time.time()
            elapsed = now - last_event_ts
            events_per_sec = round((hub.events_published - last_event_count) / elapsed, 1) if elapsed > 0 else 0.0
            last_event_count, last_event_ts = hub.events_published, now
            hub.publish("health", {
                "cpuPct": round(psutil.cpu_percent(None), 1),
                "memPct": round(psutil.virtual_memory().percent, 1),
                "eventsPerSec": events_per_sec,
                "ssePipes": len(hub.subscribers),
                "loadersOnline": sum(1 for ok in loader_status().values() if ok),
                "uptimeSec": _uptime,
                "nextRebenchInSec": REBENCH_EVERY_S - (tick % REBENCH_EVERY_S),
            })

        # sentinel: run the REAL scanner over a sample snippet every ~7s
        if tick % 7 == 0:
            target, code = SENTINEL_SAMPLES[scan_idx % len(SENTINEL_SAMPLES)]
            scan_idx += 1
            results = full_scan(target, code)
            worst = next((r for r in results if r["verdict"] == "block"),
                         next((r for r in results if r["verdict"] == "flag"), results[0]))
            hub.publish("scan", worst)
            log("sentinel", "sentinel",
                f"pre-flight {target} — {worst['check']}: {worst['verdict'].upper()}")
            node_event("risk", f"pre-flight {target} — {worst['check']}: {worst['verdict']}", tool_call=True)


def sse_format(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
