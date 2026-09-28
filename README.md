# ⚡ AetherQuant

> **Agentic Alpha Generation & Quantitative Trading Platform** — formerly *Vibe-Trading*.
> An LLM-native quant research stack: a ReAct agent core with persistent memory and
> self-modifying skills, a 456-factor Alpha Zoo (20 live), 7 backtest engines over 7 real data
> loaders, swarm DAG orchestration, and an adversarial security sandbox that
> pre-flights every line of agent-written code.

---

## Monorepo Layout

```
aetherquant/
├── agent/                          # Backend (Python)
│   ├── cli/                        #   CLI package — interactive TUI + subcommands
│   ├── api_server.py               #   FastAPI server — runs, sessions, upload, swarm, SSE
│   ├── mcp_server.py               #   MCP server — 54 tools for OpenClaw / Claude Desktop
│   │
│   └── src/
│       ├── agent/                  #   ReAct agent core
│       │   ├── loop.py             #     5-layer state compression + read/write tool batching
│       │   ├── context.py          #     system prompt + auto-recall from persistent memory
│       │   ├── skills.py           #     skill loader (79 bundled + user-created via CRUD)
│       │   ├── tools.py            #     tool base class + registry
│       │   ├── memory.py           #     lightweight workspace state per run
│       │   ├── frontmatter.py      #     shared YAML frontmatter parser
│       │   └── trace.py            #     execution trace writer
│       │
│       ├── memory/                 #   Cross-session persistent memory
│       │   └── persistent.py       #     file-based memory (~/.aetherquant/memory/)
│       │
│       ├── tools/                  #   68 auto-discovered agent tools
│       │   ├── backtest_tool.py    #     run backtests
│       │   ├── remember_tool.py    #     cross-session memory (save/recall/forget)
│       │   ├── skill_writer_tool.py#     skill CRUD (save/patch/delete/file)
│       │   ├── session_search_tool.py #  FTS5 cross-session search
│       │   ├── swarm_tool.py       #     launch swarm teams
│       │   ├── web_search_tool.py  #     DuckDuckGo web search
│       │   ├── sentinel_tool.py    #     ★ NEW: adversarial pre-flight scanner
│       │   ├── vibe_ingest_tool.py #     ★ NEW: sentiment → alt-factor pipeline
│       │   └── ...                 #     bash, file I/O, factor analysis, options, alpha bench
│       │
│       ├── factors/                #   Alpha Zoo — 456 alphas across 4 zoos
│       │   ├── base.py             #     19 operators (rank/scale/ts_*/delta/decay_linear/safe_div/vwap)
│       │   ├── registry.py         #     AST-only metadata load + lazy compute + sanity gates
│       │   ├── bench_runner.py     #     IC + alive/reversed/dead categorisation
│       │   └── zoo/                #     qlib158 (154) + alpha101 (101) + gtja191 (191) + academic (10)
│       │
│       ├── sentinel/               #   ★ NEW: Adversarial Risk & Vulnerability Sandbox
│       │   ├── lookahead.py        #     look-ahead bias detector (future-data usage in series)
│       │   ├── leakage.py          #     capital-leakage scanner (order loops, unhandled API errors)
│       │   └── dryrun.py           #     sandboxed dry-run runtime — memory-leak capture
│       │
│       ├── api/                    #   FastAPI route modules
│       │   └── alpha_routes.py     #     /alpha/list, /alpha/{id}, /alpha/bench, SSE stream
│       │
│       ├── skills/                 #   79 finance skills in 8 categories (SKILL.md each)
│       ├── swarm/                  #   Swarm DAG execution engine
│       │   └── presets/            #     29 swarm preset YAML definitions
│       ├── session/                #   Multi-turn chat + FTS5 session search
│       └── providers/              #   LLM provider abstraction
│
│   └── backtest/                   # Backtest engines
│       ├── engines/                #   7 engines + composite cross-market + options_portfolio
│       ├── loaders/                #   7 real sources: yfinance, binance, coingecko, ccxt, sina, tencent, duckdb-cache
│       │   ├── base.py             #     DataLoader Protocol
│       │   └── registry.py         #     Registry + auto-fallback chains
│       └── optimizers/             #   MVO, equal vol, max div, risk parity
│
├── frontend/                       # Web UI (React 19 + Vite + TypeScript)  ← THIS DROP
│   └── src/
│       ├── pages/                  #   Home, Agent, AlphaZoo, RunDetail, Compare, DAG, Settings
│       ├── components/             #   chat, charts, layout
│       ├── stores/                 #   Zustand state management (store.ts)
│       └── lib/                    #   SSE stream client (mock engine for dev)
│
├── Dockerfile                      # Multi-stage build
├── docker-compose.yml              # One-command deploy
├── pyproject.toml                  # Package config + CLI entrypoint
├── tools/
│   └── ci_grep_gates.sh            # rejects yaml.load / trademark / per-stock-data leaks
└── LICENSE                         # MIT
```

## Premium Features (new in AetherQuant)

| Feature | Description |
|---|---|
| **Sentinel Sandbox** | Every agent-written alpha/skill patch is pre-flighted: look-ahead-bias AST scan, capital-leakage scan, sandboxed dry-run with memory-leak capture. Verdicts stream to the UI in real time. |
| **Swarm DAG Engine** | Multi-agent ops mapped as a DAG — Data-Scraper → Math-Quant → Risk-Manager — with live state transitions and shared discoveries. |
| **Vibe Sentiment Ingestion** | Unstructured news/social sentiment → numerical momentum scores → injected into the Alpha Zoo as dynamic alternative factors. |

## Quickstart

**Backend** (FastAPI, port 8700 — real IC benchmarks, backtests, sentinel, SSE):

```bash
pip install -r aetherquant/agent/requirements.txt
python -m uvicorn api_server:app --app-dir aetherquant/agent --port 8700
```

**Frontend** (Vite proxies `/api` → `127.0.0.1:8700`):

```bash
cd aetherquant/frontend
npm install
npm run dev        # http://localhost:5174
```

**One-command deploy** (builds the SPA and serves it from the API container):

```bash
cd aetherquant && docker compose up --build
```

On load the frontend probes `/api/health`: if the backend answers it seeds from
REST and subscribes to the live `/api/events` SSE stream; if not, it falls back
to the in-browser **mock engine** (`src/lib/mockStream.ts`) so the dashboard
always runs. What's real when the backend is up:

- **Market data** — real daily OHLCV for 12 symbols (AAPL, NVDA, MSFT, TSLA,
  JPM, XOM, BTC-USD, ETH-USD, and 4 CN/HK names) fetched live from Yahoo
  Finance via `yfinance` (`src/market.py`). A disk cache under
  `agent/.cache/market/` keeps restarts fast, and any symbol that fails to
  fetch falls back to a cached copy, then to a clearly-labeled synthetic
  series as a last resort — never a silent lie. Per-symbol provenance
  (`yfinance-live` / `-cached` / `-stale-cache` / `synthetic-fallback`) is
  exposed at `/api/health` and shown as badges in Settings.
- **IC benchmarks** — daily cross-sectional spearman IC of 20 marked factors
  against forward returns computed on that real universe (the other 436
  zoo entries are AST-metadata stubs, matching the lazy-load design).
- **Backtests** — genuine long-short top/bottom-3 portfolio math with turnover
  costs on real prices; launched from AlphaZoo, chat ("backtest vibe_momo_7"),
  or POST /api/backtest.
- **Vibe sentiment** — a real-data proxy, not NLP: `tanh(10d price momentum ×
  6 + volume z-score × 0.15)` computed directly off the fetched OHLCV. Labeled
  as such in the UI (hover the Vibe Sentiment card) — it does not ingest news
  or social data.
- **Sentinel** — real `ast`-walk scanners for look-ahead bias, unbounded order
  loops, and bare excepts; try the Playground in Settings.
- **Chat** — POST /api/agent/chat runs a genuine Ollama tool-calling loop
  (`src/agent_loop.py`, model `qwen2.5:7b-instruct`) against real tools
  (`run_backtest`, `list_alphas`, `sentinel_scan`, `get_vibe`, `get_quotes`,
  a keyless DuckDuckGo `web_search`, and a DuckDB-backed `remember`/`recall`)
  whenever Ollama is reachable at `localhost:11434` — `/api/health.ollamaActive`
  reports this live, real per-call check, never hardcoded. Falls back to a
  templated (but still real-data) reply generator when Ollama or the model
  isn't available, so the app degrades gracefully rather than breaking.
- **Dashboard equity + top metrics** — "Aggregate Equity" is a real
  forward-advancing paper-trading NAV (`src/paper/engine.py`): 5
  equal-notional paper books (one per engine), positions opened/rebalanced
  daily off real cross-sectional ranking, marked to market from a live
  Binance ticker (crypto), the live sina/tencent CN quote (CN legs), or the
  latest cached daily close (US/HK legs) — never a replayed/looped
  historical backtest. Alpha Yield / Sharpe / Max DD on the metrics strip
  still reflect the best seeded backtest's real numbers (a separate stat
  from the live paper NAV). Nothing on the dashboard is
  `random.uniform()`-sourced — there is no cosmetic/scripted layer left.
- **The pipeline DAG is real telemetry** (`stream.py:SESSION` +
  `node_event`) — the 6 nodes are the actual pipeline stages (loader
  probes/quote refreshes, vibe recompute, factor re-bench, sentinel scans,
  paper marks, and the Ollama chat orchestrator), and their
  activity/status/toolCalls only change when the corresponding real
  subsystem does real work. `tokensUsed` only ever increments with genuine
  Ollama `prompt_eval_count`/`eval_count` from actual chat calls — it stays
  0 until you chat. Edges pulse only when real work flows. `simulated:
  false` on the wire; the SIMULATED badge only appears in the offline
  in-browser mock fallback (which is labeled as such).
- **Data Loaders panel** — 8 loaders have real fetch code (`market.py`):
  `yfinance`, `binance`, `coingecko`, `ccxt` (via KuCoin; was Kraken until
  Kraken's edge started refusing this network), `sina`, `tencent`,
  `duckdb-cache`, `binance-funding` (real perp funding-rate history, backs
  the `derivatives_perp` engine below). Each symbol tries the most
  authentic source first (a crypto exchange for crypto, an unofficial CN
  quote API for CN equities) before falling back to yfinance, then a
  DuckDB-backed disk cache, then synthetic data as an absolute last resort.
  `online` is a **live reachability probe** — a genuine lightweight request
  against each loader's real endpoint at startup and every 5 minutes
  (`probe_all_loaders`), never a hardcoded flag and no longer the
  confusing "served data this run" semantic that showed healthy fallback
  loaders as offline. Loaders with no real code (`akshare`, `baostock`,
  `tushare`, `polygon`, `alpaca`, `quandl`, `wind`, `joinquant`) and
  loaders never actually reachable (`okx`, `eastmoney`, `fred`) were
  dropped entirely rather than kept as a roadmap list.
- **Live CN quotes** (`/api/quotes/live`) — a real-time snapshot from Sina
  (primary) / Tencent (fallback), intentionally separate from the historical
  `bars()` pipeline since it's a single tick, not a time series. Shown in
  Settings.

## Remaining honest limitations (not simulations)

Nothing in the live app is simulated anymore — every number traces to a
real computation or a real fetch. What remains are labeled limitations:

- **The DAG is 6 pipeline stages, not 6 independent LLM agents** — there is
  one real orchestrator (the Ollama tool-calling loop); the other stages
  are real subsystems (loaders, bench, sentinel, paper engine) reporting
  real activity. The UI copy says "stages", not "agents", to avoid
  overclaiming a multi-agent system.
- **The offline in-browser mock** (`frontend/src/lib/mockStream.ts`) only
  runs when the backend is unreachable, is clearly labeled ("mock
  telemetry — backend offline", `simulated: true`, SIMULATED badge), and
  exists so the UI still demonstrates itself without a server.
- **Chat template fallback** — when Ollama isn't running, replies come from
  a keyword-routed template that still reports real data and says so in
  its first line; Settings shows "template fallback" vs "Ollama · live".
- **The original architecture's agentic core mostly doesn't exist as code** —
  no `skills/`, `swarm/` execution engine, `mcp_server.py`, or `loop.py`.
  `src/agent_loop.py`, `src/tools/` (web_search, memory), `src/paper/`, and
  `src/backtest/engines/` are real; `backtest/`, `factors/`, `sentinel/`,
  and `market.py` were already real.

## What used to be fake and is now real (fixed 2026-07-03)

- **IC no longer jitters.** The old `jitter_tick()` applied `random.uniform()`
  noise to alpha IC every ~2s. It's gone — `bench_all()` now runs a real
  spearman-IC recompute every `REBENCH_EVERY_S` (300s) against whatever
  market data is currently cached, and legitimately returns identical
  numbers between real data refreshes (that's correct behavior for a real
  statistic, not staleness).
- **The zoo count is honest.** "458 factors" was a hardcoded aspirational
  dict with zero code behind 437 of them. `/api/health` now separates
  `zooLiveCounts` (real, == the factors actually implemented — currently 20)
  from `zooPlannedCounts` (roadmap only), and the UI never merges them into
  one misleading number.
- **CPU/MEM are real** `psutil` readings (system-wide utilization), not
  `random.randint()`.
- **`eventsPerSec`** replaces the old fake `tokensPerSec` — it's a genuine
  count of SSE events the hub published, divided by real elapsed time.
- **`loadersOnline`** now reports loaders that actually served data *this
  run*, not the wired-but-not-necessarily-succeeding count.
