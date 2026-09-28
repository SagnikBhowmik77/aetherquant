"""Real chat backend: a genuine LLM tool-calling loop over this app's
actual functions. Two real providers, picked at call time:

  - Groq (hosted, free tier) when GROQ_API_KEY is set — used in the cloud
    deployment, where a local model can't fit in the free instance's RAM.
  - Ollama at localhost:11434 — used for local development.

Falls back to a templated (but real-data-backed) reply generator only when
neither is reachable, and that reply says so in its first line — never a
fake "thinking" delay pretending a model ran when one didn't.

This intentionally does NOT claim to be 6 independent reasoning agents:
it's one real orchestrator LLM making real tool calls; the other pipeline
DAG stages are real subsystems (see stream.py).
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import AsyncIterator

import httpx

from .backtest.engine import run_backtest
from .factors.registry import REGISTRY, ZOO_PLANNED_COUNTS, mean_ic
from .market import UNIVERSE, aggregate_vibe, live_quotes, sentiment, source_of
from .sentinel.scanner import full_scan
from .tools import memory, web_search

OLLAMA_URL = "http://localhost:11434"
MODEL = "qwen2.5:7b-instruct"
GROQ_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
MAX_TOOL_ITERATIONS = 4


def _groq_key() -> str | None:
    return os.environ.get("GROQ_API_KEY") or None


# reachability is cached — /api/health calls this on every request, and an
# uncached HTTP round-trip per health call made the endpoint slow enough
# that the frontend's startup probe could time out. Still a real check,
# just rate-limited (Groq longer, so health polling can't eat into its
# free-tier rate limits).
_PROVIDER_CACHE: tuple[str, float] | None = None
_OLLAMA_TTL_S = 10.0
_GROQ_TTL_S = 60.0


def _groq_reachable(key: str) -> bool:
    try:
        r = httpx.get(f"{GROQ_URL}/models", headers={"Authorization": f"Bearer {key}"}, timeout=5.0)
        return r.status_code == 200
    except Exception:
        return False


def _ollama_reachable() -> bool:
    try:
        # 3s, not 1s: /api/tags genuinely takes >1s at times locally
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


def llm_provider() -> str:
    """'groq' | 'ollama' | 'none' — which real LLM is reachable right now."""
    global _PROVIDER_CACHE
    now = time.monotonic()
    if _PROVIDER_CACHE is not None:
        provider, at = _PROVIDER_CACHE
        ttl = _GROQ_TTL_S if provider == "groq" else _OLLAMA_TTL_S
        if now - at < ttl:
            return provider
    key = _groq_key()
    if key and _groq_reachable(key):
        provider = "groq"
    elif _ollama_reachable():
        provider = "ollama"
    else:
        provider = "none"
    _PROVIDER_CACHE = (provider, now)
    return provider


def ollama_available() -> bool:
    return llm_provider() == "ollama"


# ── real tools the LLM can actually call — every one wraps a function
# that already exists elsewhere in this app, nothing new invented here ──

def _tool_run_backtest(factorId: str, engine: str = "cross_market", days: int = 250) -> dict:
    run = run_backtest(factorId, engine, days)
    return {"id": run["id"], "engine": run["engine"], "factorName": run["factorName"], "metrics": run["metrics"]}


def _tool_list_alphas(limit: int = 5) -> dict:
    alphas = sorted(REGISTRY.values(), key=lambda a: abs(a["ic"]), reverse=True)[:limit]
    return {"meanIC": mean_ic(), "top": [
        {"id": a["id"], "name": a["name"], "ic": a["ic"], "lifecycle": a["lifecycle"]} for a in alphas
    ]}


def _tool_sentinel_scan(target: str, code: str) -> dict:
    return {"results": full_scan(target, code)}


def _tool_get_vibe(symbol: str | None = None) -> dict:
    if symbol and symbol in UNIVERSE:
        return {"symbol": symbol, "vibe": round(sentiment(symbol)[-1], 4)}
    return {"aggregateVibe": aggregate_vibe()}


def _tool_get_quotes() -> dict:
    return live_quotes()


def _tool_web_search(query: str) -> dict:
    return {"results": web_search.search(query)}


def _tool_remember(key: str, value: str) -> dict:
    return {"saved": memory.remember(key, value)}


def _tool_recall(key: str) -> dict:
    return {"value": memory.recall(key)}


TOOLS = {
    "run_backtest": _tool_run_backtest,
    "list_alphas": _tool_list_alphas,
    "sentinel_scan": _tool_sentinel_scan,
    "get_vibe": _tool_get_vibe,
    "get_quotes": _tool_get_quotes,
    "web_search": _tool_web_search,
    "remember": _tool_remember,
    "recall": _tool_recall,
}

TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "run_backtest",
        "description": "Run a real cross-sectional backtest for a given factor id and engine.",
        "parameters": {"type": "object", "properties": {
            "factorId": {"type": "string", "description": "Factor id, e.g. q158_roc20"},
            "engine": {"type": "string", "enum": ["spot_basic", "cross_market", "options_portfolio", "multi_asset", "derivatives_perp"]},
            "days": {"type": "integer", "description": "Backtest window in trading days"},
        }, "required": ["factorId"]},
    }},
    {"type": "function", "function": {
        "name": "list_alphas",
        "description": "List the top real alpha factors currently benched, ranked by absolute IC.",
        "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}},
    }},
    {"type": "function", "function": {
        "name": "sentinel_scan",
        "description": "Run the real sentinel scanner (look-ahead bias, capital leakage, dry-run) over a Python snippet.",
        "parameters": {"type": "object", "properties": {
            "target": {"type": "string"}, "code": {"type": "string"},
        }, "required": ["target", "code"]},
    }},
    {"type": "function", "function": {
        "name": "get_vibe",
        "description": "Real momentum/volume 'vibe' proxy (not NLP sentiment) for a symbol, or the universe aggregate if no symbol given.",
        "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}}},
    }},
    {"type": "function", "function": {
        "name": "get_quotes",
        "description": "Real-time CN equity quote snapshot (sina/tencent).",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "web_search",
        "description": "Real keyless web search (DuckDuckGo) for current information not in this app's own data.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "remember",
        "description": "Save a note to persistent cross-session memory.",
        "parameters": {"type": "object", "properties": {
            "key": {"type": "string"}, "value": {"type": "string"},
        }, "required": ["key", "value"]},
    }},
    {"type": "function", "function": {
        "name": "recall",
        "description": "Recall a previously saved note from persistent cross-session memory.",
        "parameters": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]},
    }},
]

SYSTEM_PROMPT = (
    "You are the AetherQuant orchestrator, a quant research assistant with real tools: "
    "run backtests, list alpha factors, scan code for risk, read market vibe, get CN quotes, "
    "search the web, and save/recall notes. Use a tool whenever the user's request calls for "
    "real data or a real action rather than guessing. Be concise."
)


async def _call_llm(provider: str, messages: list[dict]) -> tuple[dict, int]:
    """One real completion round-trip. Returns (assistant_message,
    real_token_count) normalized across the two wire formats."""
    async with httpx.AsyncClient(timeout=45.0) as client:
        if provider == "groq":
            r = await client.post(
                f"{GROQ_URL}/chat/completions",
                headers={"Authorization": f"Bearer {_groq_key()}"},
                json={"model": GROQ_MODEL, "messages": messages, "tools": TOOL_SCHEMAS,
                      "tool_choice": "auto", "temperature": 0.2},
            )
            r.raise_for_status()
            data = r.json()
            tokens = int((data.get("usage") or {}).get("total_tokens") or 0)
            return data["choices"][0]["message"], tokens
        r = await client.post(f"{OLLAMA_URL}/api/chat", json={
            "model": MODEL, "messages": messages, "tools": TOOL_SCHEMAS, "stream": False,
        })
        r.raise_for_status()
        data = r.json()
        tokens = int(data.get("prompt_eval_count") or 0) + int(data.get("eval_count") or 0)
        return data.get("message", {}), tokens


async def _llm_reply(provider: str, message: str, log_fn) -> str:
    # real DAG telemetry: orchestrator tokens/toolCalls only ever move with
    # genuine provider usage counts from these calls (see stream.node_event)
    from .stream import node_event

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": message},
    ]
    for _ in range(MAX_TOOL_ITERATIONS):
        msg, real_tokens = await _call_llm(provider, messages)
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            node_event("orch", f'answered via {provider}: "{message[:40]}"', tokens=real_tokens)
            return (msg.get("content") or "").strip() or f"(empty response from {provider})"

        # echo the assistant turn back verbatim-ish: OpenAI-format providers
        # require the tool_calls (with ids) to precede the tool results
        messages.append({"role": "assistant", "content": msg.get("content") or "",
                         "tool_calls": tool_calls})
        node_event("orch", f"{provider}: reasoning over {len(tool_calls)} tool call(s)", tokens=real_tokens)
        for call in tool_calls:
            fn = call.get("function", {})
            name = fn.get("name")
            args = fn.get("arguments") or {}
            if isinstance(args, str):  # OpenAI format sends a JSON string
                try:
                    args = json.loads(args) or {}
                except Exception:
                    args = {}
            handler = TOOLS.get(name)
            if handler is None:
                result = {"error": f"unknown tool: {name}"}
            else:
                try:
                    result = await asyncio.to_thread(handler, **args)
                    log_fn("tool", name, f"chat-invoked via {provider}, args={args}")
                    node_event("orch", f"tool: {name}", tool_call=True)
                except Exception as e:
                    result = {"error": str(e)}
            tool_msg = {"role": "tool", "content": json.dumps(result, default=str)}
            if call.get("id"):
                tool_msg["tool_call_id"] = call["id"]
            messages.append(tool_msg)
    return "Hit the per-turn tool-call limit — try a narrower question."


def _compose_reply_fallback(message: str, log_fn) -> str:
    """Real-data-backed templated reply, used only when no LLM is
    unreachable (or a live call to it fails) — every number here is still
    genuinely computed, only the reply's phrasing is scripted rather than
    LLM-authored."""
    msg = message.lower()
    alphas = sorted(REGISTRY.values(), key=lambda a: abs(a["ic"]), reverse=True)
    top = alphas[0]
    alive = sum(1 for a in REGISTRY.values() if a["lifecycle"] == "alive")

    if any(k in msg for k in ("backtest", "run", "test")):
        fid = next((a["id"] for a in alphas if a["id"] in msg or a["name"].lower() in msg), top["id"])
        run = run_backtest(fid, "cross_market", 250)
        m = run["metrics"]
        log_fn("tool", "backtest_tool", f"chat-triggered {run['id']} on {fid}")
        return (f"(LLM unreachable — template reply, real data still) Spun up a real cross_market "
                f"backtest on **{run['factorName']}** ({fid}) — 250 sessions, long-short top/bottom 3 "
                f"of the {run['universe']}-name universe, 2bps turnover cost.\n\n"
                f"Run `{run['id']}` finished in {run['elapsedMs']}ms:\n"
                f"  · Sharpe {m['sharpe']}\n"
                f"  · Annualized {m['annRetPct']:+.1f}%\n"
                f"  · Max drawdown {m['maxDrawdownPct']:.1f}%\n"
                f"  · Hit rate {m['winRatePct']}%\n\n"
                f"Full NAV series and trace are in RunDetail → {run['id']}.")
    if any(k in msg for k in ("alpha", "ic", "factor", "zoo")):
        lines = "\n".join(f"  {i+1}. {a['name']} ({a['zoo']}) — IC {a['ic']:+.4f}, ICIR {a['icir']:.2f}, {a['lifecycle']}"
                          for i, a in enumerate(alphas[:5]))
        planned_total = sum(ZOO_PLANNED_COUNTS.values())
        return (f"(LLM unreachable — template reply, real data still) {len(REGISTRY)} factors are "
                f"actually implemented and benched right now (the {planned_total}-factor target roster "
                f"is mostly unbuilt — real count only): mean IC {mean_ic():+.4f}, {alive} alive.\n\n"
                f"Top by |IC|:\n{lines}\n\n"
                f"Say \"backtest {top['id']}\" and I'll run it through the engine for real.")
    if any(k in msg for k in ("vibe", "sentiment", "news")):
        live_n = sum(1 for s in UNIVERSE if not source_of(s).startswith("synthetic"))
        return (f"(LLM unreachable — template reply, real data still) Vibe score is a real-data "
                f"proxy, not NLP sentiment: tanh(10d momentum × 6 + volume z-score × 0.15), recomputed "
                f"per symbol off actual closes/volume ({live_n}/{len(UNIVERSE)} symbols live right now). "
                f"Aggregate vibe is {aggregate_vibe():+.4f} right now.")
    if any(k in msg for k in ("sentinel", "risk", "scan", "security")):
        return ("(LLM unreachable — template reply) Sentinel pre-flights every agent-written script "
                "with three passes: an AST walk for look-ahead bias, a capital-leakage scan for unbounded "
                "order loops and bare excepts, and a compile-gated dry run. Try it in Settings → "
                "Sentinel Playground, or POST /api/sentinel/scan.")
    return (f"No LLM is reachable right now, so this reply is templated rather than LLM-authored — "
            f"the data is still real. Zoo mean IC {mean_ic():+.4f} with {alive}/{len(REGISTRY)} marked "
            f"factors alive; top performer is {top['name']} at {top['ic']:+.4f}. "
            f"Ask me about **alphas**, **backtests**, **vibe sentiment**, or the **sentinel** — or "
            f"set GROQ_API_KEY (or run Ollama locally) for real LLM-driven replies.")


async def chat_reply(message: str, log_fn) -> AsyncIterator[str]:
    provider = await asyncio.to_thread(llm_provider)
    if provider != "none":
        try:
            text = await _llm_reply(provider, message, log_fn)
        except Exception as e:
            log_fn("warn", "agent_loop", f"{provider} call failed mid-turn, falling back to template: {e}")
            text = _compose_reply_fallback(message, log_fn)
    else:
        text = _compose_reply_fallback(message, log_fn)

    # constant small pacing for front-end readability — deliberately NOT a
    # randomized "token latency" imitation; the text is already complete
    for word in text.split(" "):
        yield word + " "
        await asyncio.sleep(0.012)
