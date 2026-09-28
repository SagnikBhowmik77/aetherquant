"""Real market data via a multi-source loader chain with an honest fallback.

Each symbol tries the most authentic real source first — a crypto exchange
for crypto, an unofficial-but-widely-used CN quote API for CN equities —
before falling back to yfinance, then a DuckDB-backed disk cache, then a
clearly-labeled synthetic series as an absolute last resort. Whichever tier
actually served a symbol is tracked in `_SOURCE` and each named loader's
real success/failure this run is tracked in `LOADER_STATUS`, both exposed
at /api/health so nothing is ever silently faked (see the loaders panel in
Settings — a loader only shows green if it genuinely returned data).
"""

from __future__ import annotations

import json
import math
import random
import statistics
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

DAYS = 500
DAY_MS = 86_400_000
CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "market"
CACHE_DB = CACHE_DIR / "cache.duckdb"
CACHE_TTL_SEC = 6 * 3600
MIN_ROWS = 60
HTTP_TIMEOUT = 8
UA = {"User-Agent": "Mozilla/5.0"}

# display symbol -> actual Yahoo Finance ticker (yfinance is the universal
# fallback for every symbol, since it alone covers all 3 asset classes here)
YF_MAP = {
    "600519.SH": "600519.SS", "000858.SZ": "000858.SZ", "601318.SH": "601318.SS",
    "0700.HK": "0700.HK",
    "AAPL": "AAPL", "NVDA": "NVDA", "MSFT": "MSFT", "TSLA": "TSLA",
    "JPM": "JPM", "XOM": "XOM",
    "BTC-USDT": "BTC-USD", "ETH-USDT": "ETH-USD",
}
UNIVERSE = list(YF_MAP.keys())

CRYPTO = {"BTC-USDT", "ETH-USDT"}
CN_QUOTE_MAP = {"600519.SH": "sh600519", "000858.SZ": "sz000858", "601318.SH": "sh601318"}

# loaders with real fetch code that are actually reachable — "online" is
# computed per-run from actual attempts (LOADER_STATUS), never hardcoded
# true. Loaders with no code (akshare, baostock, tushare, polygon, alpaca,
# quandl, wind, joinquant) and loaders whose code was never reachable from
# any deployment (okx, eastmoney, fred) have been dropped entirely rather
# than kept around as a roadmap list — this app only lists what it can
# genuinely serve right now.
LOADERS = ["yfinance", "binance", "coingecko", "ccxt", "sina", "tencent", "duckdb-cache", "binance-funding"]

LOADER_STATUS: dict[str, bool] = {n: False for n in LOADERS}
_BARS: dict[str, list[dict]] = {}
_SENT: dict[str, list[float]] = {}
_SOURCE: dict[str, str] = {}
_QUOTES: dict[str, dict] = {}
_FUNDING: dict[str, list[dict]] = {}


def _http_get(url: str, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(url, headers=headers or UA)
    return urllib.request.urlopen(req, timeout=HTTP_TIMEOUT).read()


# ── DuckDB-backed disk cache (real local infra, not a third-party API) ──

def _open_db():
    import duckdb
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(CACHE_DB))
    con.execute("CREATE TABLE IF NOT EXISTS bars "
               "(symbol VARCHAR, ts BIGINT, open DOUBLE, high DOUBLE, low DOUBLE, "
               "close DOUBLE, volume DOUBLE)")
    con.execute("CREATE TABLE IF NOT EXISTS cache_meta "
               "(symbol VARCHAR PRIMARY KEY, fetched_at BIGINT, source VARCHAR)")
    return con


try:
    _db = _open_db()
    _db.execute("SELECT 1")
    LOADER_STATUS["duckdb-cache"] = True
except Exception as e:
    print(f"[aetherquant.market] WARNING: duckdb cache unavailable ({e}) — caching disabled")
    _db = None

# a single duckdb.Connection isn't safe for concurrent use from multiple
# threads — load_all() fetches every symbol in parallel via ThreadPoolExecutor,
# so every _db call must go through this lock (it only guards the brief
# local read/write, not the slow network fetch, so parallelism is barely
# affected). Without this, concurrent queries interleaved and returned
# type-mismatched garbage (caught during testing: a str where an int was
# expected in _cache_is_fresh).
_db_lock = threading.Lock()


def _write_cache(symbol: str, bars: list[dict], source: str) -> None:
    if _db is None:
        return
    with _db_lock:
        _db.execute("DELETE FROM bars WHERE symbol = ?", [symbol])
        _db.executemany(
            "INSERT INTO bars VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(symbol, b["ts"], b["open"], b["high"], b["low"], b["close"], b["volume"]) for b in bars],
        )
        _db.execute("DELETE FROM cache_meta WHERE symbol = ?", [symbol])
        _db.execute("INSERT INTO cache_meta VALUES (?, ?, ?)", [symbol, int(time.time()), source])


def _read_cache(symbol: str) -> list[dict] | None:
    if _db is None:
        return None
    with _db_lock:
        rows = _db.execute(
            "SELECT ts, open, high, low, close, volume FROM bars WHERE symbol = ? ORDER BY ts", [symbol]
        ).fetchall()
    if len(rows) < MIN_ROWS:
        return None
    return [{"ts": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]} for r in rows]


def _cache_source(symbol: str) -> str:
    if _db is None:
        return "cache"
    with _db_lock:
        row = _db.execute("SELECT source FROM cache_meta WHERE symbol = ?", [symbol]).fetchone()
    return row[0] if row else "cache"


def _cache_is_fresh(symbol: str) -> bool:
    if _db is None:
        return False
    with _db_lock:
        row = _db.execute("SELECT fetched_at FROM cache_meta WHERE symbol = ?", [symbol]).fetchone()
    return row is not None and (time.time() - row[0]) < CACHE_TTL_SEC


# ── real fetchers — each returns bars or None, never raises ──

def _fetch_yfinance(symbol: str) -> list[dict] | None:
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        hist = yf.Ticker(YF_MAP.get(symbol, symbol)).history(period="2y", interval="1d")
        if hist is None or len(hist) < MIN_ROWS:
            return None
        bars = [
            {"ts": int(idx.timestamp() * 1000), "open": float(row["Open"]), "high": float(row["High"]),
             "low": float(row["Low"]), "close": float(row["Close"]), "volume": float(row["Volume"])}
            for idx, row in hist.iterrows()
        ]
        return bars[-DAYS:]
    except Exception:
        return None


def _fetch_binance(symbol: str) -> list[dict] | None:
    sym = {"BTC-USDT": "BTCUSDT", "ETH-USDT": "ETHUSDT"}.get(symbol)
    if not sym:
        return None
    try:
        raw = _http_get(f"https://api.binance.com/api/v3/klines?symbol={sym}&interval=1d&limit={DAYS}")
        rows = json.loads(raw)
        if not rows or len(rows) < MIN_ROWS:
            return None
        return [{"ts": int(r[0]), "open": float(r[1]), "high": float(r[2]),
                 "low": float(r[3]), "close": float(r[4]), "volume": float(r[5])} for r in rows]
    except Exception:
        return None


def _fetch_binance_funding(symbol: str) -> list[dict] | None:
    """Real historical perp funding-rate payments — Binance USDT-M futures,
    free and keyless. Backs the derivatives_perp engine's funding-carry
    strategy (see backtest/engines/derivatives_perp.py) — never a made-up
    carry number."""
    sym = {"BTC-USDT": "BTCUSDT", "ETH-USDT": "ETHUSDT"}.get(symbol)
    if not sym:
        return None
    try:
        raw = _http_get(f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={sym}&limit=1000")
        rows = json.loads(raw)
        if not rows:
            return None
        result = [{"ts": int(r["fundingTime"]), "rate": float(r["fundingRate"])} for r in rows]
        LOADER_STATUS["binance-funding"] = True
        return result
    except Exception:
        LOADER_STATUS.setdefault("binance-funding", False)
        return None


def funding_rates(symbol: str) -> list[dict]:
    """Real Binance perp funding history for symbol, or [] if unavailable
    (crypto only — no funding market exists for equities)."""
    if symbol not in _FUNDING:
        _FUNDING[symbol] = _fetch_binance_funding(symbol) or []
    return _FUNDING[symbol]


def _fetch_coingecko(symbol: str) -> list[dict] | None:
    coin = {"BTC-USDT": "bitcoin", "ETH-USDT": "ethereum"}.get(symbol)
    if not coin:
        return None
    try:
        ohlc = json.loads(_http_get(f"https://api.coingecko.com/api/v3/coins/{coin}/ohlc?vs_currency=usd&days=365"))
        if len(ohlc) < MIN_ROWS:
            return None
        vol_by_day: dict[int, float] = {}
        try:
            chart = json.loads(
                _http_get(f"https://api.coingecko.com/api/v3/coins/{coin}/market_chart?vs_currency=usd&days=365")
            )
            for ts, v in chart.get("total_volumes", []):
                vol_by_day[int(ts) // DAY_MS] = float(v)
        except Exception:
            pass  # OHLC without volume is still real data — just less complete
        return [
            {"ts": int(ts), "open": float(o), "high": float(h), "low": float(low), "close": float(c),
             "volume": vol_by_day.get(int(ts) // DAY_MS, 0.0)}
            for ts, o, h, low, c in ohlc
        ]
    except Exception:
        return None


def _fetch_ccxt(symbol: str) -> list[dict] | None:
    # KuCoin via ccxt (was Kraken — Kraken's edge started refusing
    # connections from residential IPs here; KuCoin is keyless, free, and
    # verified reachable, and quotes the same real USDT pairs)
    pair = {"BTC-USDT": "BTC/USDT", "ETH-USDT": "ETH/USDT"}.get(symbol)
    if not pair:
        return None
    try:
        import ccxt
        ex = ccxt.kucoin()
        rows = ex.fetch_ohlcv(pair, timeframe="1d", limit=DAYS)
        if not rows or len(rows) < MIN_ROWS:
            return None
        return [{"ts": int(r[0]), "open": float(r[1]), "high": float(r[2]),
                 "low": float(r[3]), "close": float(r[4]), "volume": float(r[5])} for r in rows]
    except Exception:
        return None


def _fetch_chain(symbol: str) -> list[tuple[str, "callable"]]:
    if symbol in CRYPTO:
        return [("binance", _fetch_binance), ("coingecko", _fetch_coingecko),
                ("ccxt", _fetch_ccxt), ("yfinance", _fetch_yfinance)]
    return [("yfinance", _fetch_yfinance)]


def _gen_synthetic(symbol: str, days: int = DAYS) -> list[dict]:
    """Deterministic geometric-brownian-motion fallback — last resort only."""
    rnd = random.Random(abs(hash(symbol)) & 0xFFFF)
    price = 40.0 + rnd.random() * 260.0
    drift = rnd.uniform(-0.0002, 0.0007)
    vol = rnd.uniform(0.011, 0.026)
    bars: list[dict] = []
    now = int(time.time() * 1000)
    for i in range(days):
        regime = 1.0 + 0.6 * math.sin(i / rnd.uniform(55, 90))
        ret = rnd.gauss(drift * regime, vol)
        o = price
        c = price * math.exp(ret)
        h = max(o, c) * (1 + abs(rnd.gauss(0, 0.004)))
        low = min(o, c) * (1 - abs(rnd.gauss(0, 0.004)))
        v = rnd.uniform(1.0e6, 6.0e6) * (1 + 2.5 * abs(ret) / vol)
        bars.append({"ts": now - (days - 1 - i) * DAY_MS,
                     "open": o, "high": h, "low": low, "close": c, "volume": v})
        price = c
    return bars


def _load_one(symbol: str) -> tuple[str, list[dict], str]:
    if _cache_is_fresh(symbol):
        cached = _read_cache(symbol)
        if cached:
            return symbol, cached, f"{_cache_source(symbol)}-cached"

    for name, fetcher in _fetch_chain(symbol):
        result = fetcher(symbol)
        if result:
            _write_cache(symbol, result, name)
            LOADER_STATUS[name] = True
            return symbol, result, f"{name}-live"
        else:
            LOADER_STATUS.setdefault(name, False)

    stale = _read_cache(symbol)
    if stale:
        return symbol, stale, f"{_cache_source(symbol)}-stale-cache"

    return symbol, _gen_synthetic(symbol), "synthetic-fallback"


def load_all() -> None:
    """Fetch every symbol in parallel — call once at startup."""
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=len(UNIVERSE)) as ex:
        futures = [ex.submit(_load_one, s) for s in UNIVERSE]
        for fut in as_completed(futures):
            symbol, bars, source = fut.result()
            _BARS[symbol] = bars
            _SOURCE[symbol] = source

    _load_quotes()

    real_n = sum(1 for s in _SOURCE.values() if not s.startswith("synthetic"))
    print(f"[aetherquant.market] loaded {len(UNIVERSE)} symbols "
          f"({real_n} real) in {time.perf_counter() - t0:.1f}s")
    for sym, src in _SOURCE.items():
        print(f"[aetherquant.market]   {sym:12s} <- {src}")
        if src == "synthetic-fallback":
            print(f"[aetherquant.market] WARNING: {sym} fell back to synthetic data")


def bars(symbol: str) -> list[dict]:
    if symbol not in _BARS:
        load_all()
    return _BARS[symbol]


def source_of(symbol: str) -> str:
    return _SOURCE.get(symbol, "unknown")


def loader_status() -> dict[str, bool]:
    return dict(LOADER_STATUS)


# ── real per-loader reachability probes ─────────────────────────────
# LOADER_STATUS used to mean "served bar data this run", which honestly
# but confusingly showed fallback loaders (coingecko/ccxt/tencent) and
# cache-skipped primaries as offline even when perfectly reachable. Each
# probe below is a genuine lightweight request against the loader's real
# endpoint — a loader shows green iff its probe just succeeded, never a
# hardcoded flag. Run at startup and periodically from stream.telemetry_loop.

def _probe_yfinance() -> bool:
    try:
        import yfinance as yf
        hist = yf.Ticker("AAPL").history(period="5d", interval="1d")
        return hist is not None and len(hist) > 0
    except Exception:
        return False


def _probe_binance() -> bool:
    try:
        _http_get("https://api.binance.com/api/v3/ping")
        return True
    except Exception:
        return False


def _probe_coingecko() -> bool:
    try:
        _http_get("https://api.coingecko.com/api/v3/ping")
        return True
    except Exception:
        return False


def _probe_ccxt() -> bool:
    try:
        import ccxt
        ccxt.kucoin().fetch_time()
        return True
    except Exception:
        return False


def _probe_sina() -> bool:
    return _fetch_sina_quote("600519.SH") is not None


def _probe_tencent() -> bool:
    return _fetch_tencent_quote("600519.SH") is not None


def _probe_duckdb() -> bool:
    if _db is None:
        return False
    try:
        with _db_lock:
            _db.execute("SELECT 1")
        return True
    except Exception:
        return False


def _probe_binance_funding() -> bool:
    try:
        rows = json.loads(_http_get("https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=1"))
        return bool(rows)
    except Exception:
        return False


_PROBES = {
    "yfinance": _probe_yfinance,
    "binance": _probe_binance,
    "coingecko": _probe_coingecko,
    "ccxt": _probe_ccxt,
    "sina": _probe_sina,
    "tencent": _probe_tencent,
    "duckdb-cache": _probe_duckdb,
    "binance-funding": _probe_binance_funding,
}


def _probe_with_retry(fn) -> bool:
    """One retry on failure — a single transient network hiccup shouldn't
    paint a genuinely reachable loader offline until the next probe cycle."""
    if fn():
        return True
    time.sleep(1.0)
    return fn()


def probe_all_loaders() -> dict[str, bool]:
    """Probe every loader in parallel with a real request each; updates
    LOADER_STATUS in place and returns the fresh results. Blocking —
    callers on the event loop should run this in a thread."""
    with ThreadPoolExecutor(max_workers=len(_PROBES)) as ex:
        futures = {name: ex.submit(_probe_with_retry, fn) for name, fn in _PROBES.items()}
        for name, fut in futures.items():
            try:
                LOADER_STATUS[name] = bool(fut.result(timeout=2 * HTTP_TIMEOUT + 6))
            except Exception:
                LOADER_STATUS[name] = False
    return dict(LOADER_STATUS)


# ── real-time CN quote snapshot (sina primary, tencent fallback) —
# genuinely distinct from the historical bars() pipeline: a single live
# tick, not a time series, and presented to the frontend as exactly that ──

def _fetch_sina_quote(symbol: str) -> dict | None:
    code = CN_QUOTE_MAP.get(symbol)
    if not code:
        return None
    try:
        raw = _http_get(f"https://hq.sinajs.cn/list={code}",
                        {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"})
        text = raw.decode("gbk", errors="replace")
        inner = text.split('"')[1]
        p = inner.split(",")
        if len(p) < 6:
            return None
        LOADER_STATUS["sina"] = True
        return {"name": p[0], "open": float(p[1]), "prevClose": float(p[2]),
                "price": float(p[3]), "high": float(p[4]), "low": float(p[5]),
                "source": "sina", "ts": int(time.time() * 1000)}
    except Exception:
        LOADER_STATUS.setdefault("sina", False)
        return None


def _fetch_tencent_quote(symbol: str) -> dict | None:
    code = CN_QUOTE_MAP.get(symbol)
    if not code:
        return None
    try:
        raw = _http_get(f"https://qt.gtimg.cn/q={code}")
        text = raw.decode("gbk", errors="replace")
        inner = text.split('"')[1]
        p = inner.split("~")
        if len(p) < 6:
            return None
        LOADER_STATUS["tencent"] = True
        return {"name": p[1], "price": float(p[3]), "prevClose": float(p[4]),
                "open": float(p[5]), "source": "tencent", "ts": int(time.time() * 1000)}
    except Exception:
        LOADER_STATUS.setdefault("tencent", False)
        return None


def _load_quotes() -> None:
    for symbol in CN_QUOTE_MAP:
        q = _fetch_sina_quote(symbol) or _fetch_tencent_quote(symbol)
        if q:
            _QUOTES[symbol] = q


def refresh_quotes() -> None:
    """Re-fetch the CN live-quote snapshot. `load_all()` only calls
    `_load_quotes()` once at startup — without a periodic refresh, the CN
    legs of paper-trading mark-to-market (and /api/quotes/live) would go
    stale forever after boot instead of genuinely ticking. Called
    periodically from stream.py's telemetry_loop."""
    _load_quotes()


def live_quotes() -> dict[str, dict]:
    return dict(_QUOTES)


# ── live price tiers for paper-trading mark-to-market (agent/src/paper) —
# crypto gets a genuinely live poll (short-cached to avoid hammering the
# endpoint), CN gets the existing live sina/tencent quote, everything else
# marks off the latest cached daily close (only moves when that ~6h cache
# actually refreshes — never interpolated or invented in between) ──

_TICKER_CACHE: dict[str, tuple[float, float]] = {}
TICKER_TTL_SEC = 12


def _fetch_binance_ticker(symbol: str) -> float | None:
    sym = {"BTC-USDT": "BTCUSDT", "ETH-USDT": "ETHUSDT"}.get(symbol)
    if not sym:
        return None
    try:
        d = json.loads(_http_get(f"https://api.binance.com/api/v3/ticker/price?symbol={sym}"))
        return float(d["price"])
    except Exception:
        return None


def latest_price(symbol: str) -> float:
    """Best real-time-ish price available for this symbol right now."""
    if symbol in CRYPTO:
        cached = _TICKER_CACHE.get(symbol)
        if cached and time.time() - cached[1] < TICKER_TTL_SEC:
            return cached[0]
        price = _fetch_binance_ticker(symbol)
        if price is not None:
            _TICKER_CACHE[symbol] = (price, time.time())
            return price
        if cached:
            return cached[0]
    elif symbol in CN_QUOTE_MAP:
        q = _QUOTES.get(symbol)
        if q:
            return q["price"]
    b = bars(symbol)
    return b[-1]["close"] if b else 0.0


def sentiment(symbol: str) -> list[float]:
    """Momentum/volume 'vibe' proxy derived from real OHLCV — not NLP sentiment.

    tanh-squashed composite of 10-day price momentum and a volume z-score,
    computed directly off the fetched bars so it moves with the real market
    instead of a random walk.
    """
    if symbol in _SENT:
        return _SENT[symbol]

    b = bars(symbol)
    closes = [x["close"] for x in b]
    vols = [x["volume"] for x in b]
    n = len(b)
    out = [0.0] * n
    window = 20
    for t in range(n):
        lo = max(0, t - 9)
        momentum = closes[t] / closes[lo] - 1 if closes[lo] else 0.0
        vwin = vols[max(0, t - window + 1): t + 1]
        vmean = sum(vwin) / len(vwin)
        vstd = (sum((v - vmean) ** 2 for v in vwin) / len(vwin)) ** 0.5 or 1.0
        vol_z = (vols[t] - vmean) / vstd
        out[t] = math.tanh(momentum * 6 + vol_z * 0.15)
    _SENT[symbol] = out
    return out


def aggregate_vibe() -> float:
    """Mean of the real per-symbol momentum/volume proxy across the universe."""
    return round(statistics.fmean(sentiment(s)[-1] for s in UNIVERSE), 4)
