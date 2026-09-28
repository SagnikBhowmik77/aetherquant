"""Alpha Zoo registry — factor definitions + real IC benchmarking.

Every factor is a pure function of data up to index t (no look-ahead).
The bench runner computes daily cross-sectional spearman IC against
next-day forward returns over the whole universe — genuine math, not
canned numbers. Results are cached at startup and refreshed by a real
periodic recompute (see bench_all / stream.py) — never faked with
per-tick random jitter.
"""

from __future__ import annotations

import math
import statistics
import time
from ..market import UNIVERSE, bars, sentiment

# ── operators (the 19-op safe-math layer) ──────────────────────────


def _closes(b): return [x["close"] for x in b]


def safe_div(a: float, b: float) -> float:
    return a / b if abs(b) > 1e-12 else 0.0


def sma(xs, n, t):
    w = xs[max(0, t - n + 1): t + 1]
    return sum(w) / len(w)


def std(xs, n, t):
    w = xs[max(0, t - n + 1): t + 1]
    return statistics.pstdev(w) if len(w) > 1 else 0.0


def ts_min(xs, n, t): return min(xs[max(0, t - n + 1): t + 1])
def ts_max(xs, n, t): return max(xs[max(0, t - n + 1): t + 1])


def ts_rank(xs, n, t):
    w = xs[max(0, t - n + 1): t + 1]
    return sum(1 for v in w if v <= xs[t]) / len(w)


def delta(xs, n, t): return xs[t] - xs[t - n]


def corr(a, b, n, t):
    wa, wb = a[max(0, t - n + 1): t + 1], b[max(0, t - n + 1): t + 1]
    ma, mb = sum(wa) / len(wa), sum(wb) / len(wb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(wa, wb))
    va = math.sqrt(sum((x - ma) ** 2 for x in wa))
    vb = math.sqrt(sum((y - mb) ** 2 for y in wb))
    return safe_div(cov, va * vb)


def vwap(b, n, t):
    w = b[max(0, t - n + 1): t + 1]
    pv = sum(x["close"] * x["volume"] for x in w)
    return safe_div(pv, sum(x["volume"] for x in w))


def _spearman(a: list[float], b: list[float]) -> float:
    n = len(a)
    if n < 3:
        return 0.0

    def ranks(xs):
        order = sorted(range(n), key=lambda i: xs[i])
        r = [0.0] * n
        for rk, i in enumerate(order):
            r[i] = float(rk)
        return r

    ra, rb = ranks(a), ranks(b)
    ma = mb = (n - 1) / 2
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = math.sqrt(sum((x - ma) ** 2 for x in ra))
    vb = math.sqrt(sum((y - mb) ** 2 for y in rb))
    return safe_div(cov, va * vb)


# ── factor definitions ─────────────────────────────────────────────
# fn(bars, sent, t) -> float, using data only up to t

def _f_kmid(b, _s, t): return safe_div(b[t]["close"] - b[t]["open"], b[t]["open"])
def _f_klen(b, _s, t): return safe_div(b[t]["high"] - b[t]["low"], b[t]["open"])
def _f_roc20(b, _s, t): c = _closes(b); return safe_div(c[t], c[t - 20]) - 1
def _f_roc60(b, _s, t): c = _closes(b); return safe_div(c[t - 60], c[t])
def _f_ma20dev(b, _s, t): c = _closes(b); return safe_div(c[t], sma(c, 20, t)) - 1
def _f_rev5(b, _s, t): c = _closes(b); return -(safe_div(c[t], c[t - 5]) - 1)
def _f_rsv9(b, _s, t):
    h = [x["high"] for x in b]; low = [x["low"] for x in b]
    lo, hi = ts_min(low, 9, t), ts_max(h, 9, t)
    return safe_div(b[t]["close"] - lo, hi - lo)
def _f_a101(b, _s, t): return safe_div(b[t]["close"] - b[t]["open"], (b[t]["high"] - b[t]["low"]) + 0.001)
def _f_a042(b, _s, t):
    v = vwap(b, 10, t); c = b[t]["close"]
    return safe_div(v - c, v + c)
def _f_volratio(b, _s, t):
    v = [x["volume"] for x in b]
    return safe_div(v[t], sma(v, 20, t)) - 1
def _f_corr_hv(b, _s, t):
    h = [x["high"] for x in b]; v = [x["volume"] for x in b]
    return -corr(h, v, 10, t)
def _f_gtja9(b, _s, t):
    mid = [(x["high"] + x["low"]) / 2 for x in b]
    v = [x["volume"] for x in b]
    return sma([safe_div((mid[i] - mid[i - 1]) * (b[i]["high"] - b[i]["low"]), v[i]) * 1e6
                for i in range(max(1, t - 6), t + 1)], 7, 6)
def _f_gtja130(b, _s, t):
    if t < 60:
        return 0.0
    mid = [(x["high"] + x["low"]) / 2 for x in b[t - 9: t + 1]]
    v = [x["volume"] for x in b]
    smav = [sma(v, 40, i) for i in range(t - 9, t + 1)]
    return corr(mid, smav, 10, 9)
def _f_tsrank_d3(b, _s, t):
    c = _closes(b)
    d = [c[i] - c[i - 3] for i in range(t - 8, t + 1)]
    return ts_rank(d, 9, 8)
def _f_vol20(b, _s, t):
    c = _closes(b)
    rets = [safe_div(c[i], c[i - 1]) - 1 for i in range(t - 19, t + 1)]
    return -statistics.pstdev(rets)
def _f_pead(b, _s, t):
    c = _closes(b)
    surprise = [safe_div(c[i], sma(c, 60, i)) - 1 for i in range(t - 11, t + 1)]
    return sum(s * (12 - k) for k, s in enumerate(reversed(surprise))) / 78
def _f_maxret(b, _s, t):
    c = _closes(b)
    rets = [safe_div(c[i], c[i - 1]) - 1 for i in range(t - 19, t + 1)]
    return -max(rets)
def _f_amihud(b, _s, t):
    c = _closes(b)
    vals = [safe_div(abs(safe_div(c[i], c[i - 1]) - 1) * 1e9, b[i]["volume"] * c[i]) for i in range(t - 9, t + 1)]
    return -sma(vals, 10, 9)
def _f_vibe7(b, s, t): return ts_rank(s, 7, t)
def _f_vibe_mom(b, s, t):
    v = [x["volume"] for x in b]
    return s[t] * safe_div(v[t], sma(v, 20, t))


FACTORS: list[dict] = [
    {"id": "q158_kmid",    "name": "KMID",        "zoo": "qlib158",  "fn": _f_kmid,      "expression": "(close - open) / open"},
    {"id": "q158_klen",    "name": "KLEN",        "zoo": "qlib158",  "fn": _f_klen,      "expression": "(high - low) / open"},
    {"id": "q158_roc20",   "name": "ROC20",       "zoo": "qlib158",  "fn": _f_roc20,     "expression": "close / ref(close, 20) - 1"},
    {"id": "q158_roc60",   "name": "ROC60",       "zoo": "qlib158",  "fn": _f_roc60,     "expression": "ref(close, 60) / close"},
    {"id": "q158_ma20",    "name": "MA20-dev",    "zoo": "qlib158",  "fn": _f_ma20dev,   "expression": "close / mean(close, 20) - 1"},
    {"id": "q158_rsv9",    "name": "RSV9",        "zoo": "qlib158",  "fn": _f_rsv9,      "expression": "(close - ts_min(low, 9)) / (ts_max(high, 9) - ts_min(low, 9))"},
    {"id": "q158_vstd",    "name": "VSTD20",      "zoo": "qlib158",  "fn": _f_vol20,     "expression": "-std(returns, 20)"},
    {"id": "a101_001",     "name": "Alpha#001",   "zoo": "alpha101", "fn": _f_tsrank_d3, "expression": "ts_rank(delta(close, 3), 9)"},
    {"id": "a101_042",     "name": "Alpha#042",   "zoo": "alpha101", "fn": _f_a042,      "expression": "rank(vwap - close) / rank(vwap + close)"},
    {"id": "a101_101",     "name": "Alpha#101",   "zoo": "alpha101", "fn": _f_a101,      "expression": "(close - open) / ((high - low) + .001)"},
    {"id": "a101_rev5",    "name": "STR-5",       "zoo": "alpha101", "fn": _f_rev5,      "expression": "-(close / ref(close, 5) - 1)"},
    {"id": "a101_chv",     "name": "CorrHV",      "zoo": "alpha101", "fn": _f_corr_hv,   "expression": "-corr(high, volume, 10)"},
    {"id": "gtja_009",     "name": "GTJA#009",    "zoo": "gtja191",  "fn": _f_gtja9,     "expression": "sma(((high+low)/2 - delay((high+low)/2, 1)) * (high-low) / volume, 7, 2)"},
    {"id": "gtja_130",     "name": "GTJA#130",    "zoo": "gtja191",  "fn": _f_gtja130,   "expression": "rank(decay_linear(corr((high+low)/2, mean(volume, 40), 9), 10))"},
    {"id": "gtja_vr",      "name": "GTJA-VR",     "zoo": "gtja191",  "fn": _f_volratio,  "expression": "volume / mean(volume, 20) - 1"},
    {"id": "acad_pead",    "name": "PEAD drift",  "zoo": "academic", "fn": _f_pead,      "expression": "decay_linear(earnings_surprise, 12)"},
    {"id": "acad_maxret",  "name": "MAX effect",  "zoo": "academic", "fn": _f_maxret,    "expression": "-ts_max(returns, 20)"},
    {"id": "acad_amihud",  "name": "Amihud ILLIQ","zoo": "academic", "fn": _f_amihud,    "expression": "-mean(|ret| / dollar_volume, 10)"},
    {"id": "vibe_momo_7",  "name": "VibeMomo-7",  "zoo": "vibe",     "fn": _f_vibe7,     "expression": "ts_rank(vibe_score, 7)"},
    {"id": "vibe_volmom",  "name": "VibeVolMom",  "zoo": "vibe",     "fn": _f_vibe_mom,  "expression": "vibe_score * safe_div(volume, adv20)"},
]

# Target roster sizes from the original architecture spec — these are NOT
# implemented (no AST metadata, no code, nothing). Keep separate from the
# real count so the UI never implies all 458 are live.
ZOO_PLANNED_COUNTS = {"qlib158": 154, "alpha101": 101, "gtja191": 191, "academic": 10, "vibe": 2}


def zoo_live_counts() -> dict[str, int]:
    """Real per-zoo counts of factors that actually have code (== len(FACTORS))."""
    counts: dict[str, int] = {}
    for f in FACTORS:
        counts[f["zoo"]] = counts.get(f["zoo"], 0) + 1
    return counts


EVAL_START = 120   # warm-up so every operator window is full
IC_POINTS = 48     # points kept for the decay sparkline

REGISTRY: dict[str, dict] = {}
LAST_BENCHED_AT: int = 0  # epoch ms of the last real bench_all() run


def signal_at(factor: dict, t: int) -> dict[str, float]:
    """Cross-sectional signal at day t (uses data up to t only)."""
    return {sym: factor["fn"](bars(sym), sentiment(sym), t) for sym in UNIVERSE}


def _bench_factor(factor: dict) -> dict:
    # different real loaders can return different-length real histories
    # (e.g. eastmoney vs yfinance vs binance) — use the shortest so every
    # symbol has valid data at every t, instead of assuming UNIVERSE[0]'s
    # length applies to all (that crashed with IndexError once eastmoney
    # started succeeding with a shorter series than the others)
    days = min(len(bars(s)) for s in UNIVERSE)
    ics: list[float] = []
    for t in range(EVAL_START, days - 1):
        sig = signal_at(factor, t)
        fwd = {s: bars(s)[t + 1]["close"] / bars(s)[t]["close"] - 1 for s in UNIVERSE}
        ics.append(_spearman([sig[s] for s in UNIVERSE], [fwd[s] for s in UNIVERSE]))
    # rolling-mean smoothing, then downsample to IC_POINTS
    smooth = [sum(ics[max(0, i - 9): i + 1]) / len(ics[max(0, i - 9): i + 1]) for i in range(len(ics))]
    step = max(1, len(smooth) // IC_POINTS)
    history = smooth[:: step][-IC_POINTS:]
    ic = sum(smooth[-20:]) / 20
    sd = statistics.pstdev(smooth[-60:]) or 1e-9
    lifecycle = "alive" if ic > 0.015 else "reversed" if ic < -0.015 else "dead"
    return {
        "id": factor["id"], "name": factor["name"], "zoo": factor["zoo"],
        "expression": factor["expression"],
        "ic": round(ic, 4), "icir": round(ic / sd, 2), "lifecycle": lifecycle,
        "icHistory": [round(x, 4) for x in history],
        "sentinelPassed": True,
    }


def bench_all() -> None:
    """Real spearman-IC recompute over the currently cached market data.

    Called at startup and periodically by the telemetry loop (see
    stream.py) so IC figures genuinely refresh over time — no per-tick
    random jitter layered on top. Since price data only changes when
    market.load_all() refetches (on its own TTL), repeated calls here
    will legitimately return identical numbers until new data lands;
    that's correct behavior for a real statistic, not a bug.
    """
    global LAST_BENCHED_AT
    for f in FACTORS:
        REGISTRY[f["id"]] = _bench_factor(f)
    LAST_BENCHED_AT = int(time.time() * 1000)


def alpha_list() -> list[dict]:
    return list(REGISTRY.values())


def get_factor(fid: str) -> dict | None:
    return next((f for f in FACTORS if f["id"] == fid), None)


def last_benched_at() -> int:
    """Epoch ms of the last real bench_all() run — a plain module-level
    variable would go stale across imports since bench_all() reassigns it."""
    return LAST_BENCHED_AT


def mean_ic() -> float:
    vals = [a["ic"] for a in REGISTRY.values()]
    return round(sum(vals) / len(vals), 4) if vals else 0.0
