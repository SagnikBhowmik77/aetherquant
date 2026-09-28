"""Real live paper-trading engine — replaces the old replayed/looped
backtest NAV with a genuinely forward-advancing paper portfolio.

Five equal-notional paper books, one per named backtest engine, each using
the same real top/bottom-N cross-sectional ranking spot_basic itself uses
(agent/src/backtest/long_short.py's approach) — applied to the LATEST real
bar instead of historical data, so positions are opened prospectively, not
backtested. Each book is assigned the same factor its seed backtest used
(see backtest/engine.py's seed_runs()), so the 5 books genuinely diverge.

Positions persist in DuckDB (agent/.cache/agent/paper.duckdb, mirroring
market.py's cache pattern) and are rebalanced once per real calendar day.
Between rebalances, `mark_to_market()` marks currently-open positions at
whatever price tier is freshest right now (market.latest_price — live
crypto ticker, live CN quote, or last cached daily close), so NAV genuinely
moves in real time for crypto/CN legs and steps forward whenever the
US-equity cache refreshes — never a fabricated interpolation.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from ..factors.registry import get_factor, signal_at
from ..market import UNIVERSE, bars, latest_price

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".cache" / "agent"
CACHE_DB = CACHE_DIR / "paper.duckdb"
HOLD = 3
STARTING_NOTIONAL = 1_000_000.0

# same factor each engine's seed backtest uses (backtest/engine.py::seed_runs)
# — kept in sync manually since importing seed_runs's list would pull in
# the whole engines/ package for one small mapping
ENGINE_FACTORS = {
    "cross_market": "q158_roc20",
    "spot_basic": "a101_042",
    "multi_asset": "acad_pead",
    "derivatives_perp": "vibe_momo_7",
    "options_portfolio": "a101_rev5",
}


def _open_db():
    import duckdb
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(CACHE_DB))
    con.execute("CREATE TABLE IF NOT EXISTS paper_state "
               "(engine VARCHAR PRIMARY KEY, base_nav DOUBLE, last_rebalance_day BIGINT)")
    con.execute("CREATE TABLE IF NOT EXISTS paper_positions "
               "(engine VARCHAR, symbol VARCHAR, side INTEGER, entry_price DOUBLE, entry_ts BIGINT)")
    con.execute("CREATE TABLE IF NOT EXISTS paper_nav (engine VARCHAR, ts BIGINT, nav DOUBLE)")
    return con


try:
    _db = _open_db()
except Exception as e:
    print(f"[aetherquant.paper] WARNING: duckdb unavailable ({e}) — paper engine disabled")
    _db = None

_lock = threading.Lock()


def _today() -> int:
    return int(time.time()) // 86_400


def _get_state(engine: str) -> tuple[float, int]:
    with _lock:
        row = _db.execute(
            "SELECT base_nav, last_rebalance_day FROM paper_state WHERE engine = ?", [engine]
        ).fetchone()
    return (row[0], row[1]) if row else (1.0, -1)


def _set_state(engine: str, base_nav: float, day: int) -> None:
    with _lock:
        _db.execute("DELETE FROM paper_state WHERE engine = ?", [engine])
        _db.execute("INSERT INTO paper_state VALUES (?, ?, ?)", [engine, base_nav, day])


def _get_positions(engine: str) -> list[tuple[str, int, float]]:
    with _lock:
        rows = _db.execute(
            "SELECT symbol, side, entry_price FROM paper_positions WHERE engine = ?", [engine]
        ).fetchall()
    return rows


def _set_positions(engine: str, positions: list[tuple[str, int, float]]) -> None:
    now = int(time.time() * 1000)
    with _lock:
        _db.execute("DELETE FROM paper_positions WHERE engine = ?", [engine])
        _db.executemany(
            "INSERT INTO paper_positions VALUES (?, ?, ?, ?, ?)",
            [(engine, sym, side, price, now) for sym, side, price in positions],
        )


def _rank_latest(factor_id: str) -> list[tuple[str, int, float]]:
    """Real top/bottom-HOLD cross-sectional ranking at the latest available
    bar (prospective, not historical) — same style as spot_basic's ranking,
    applied to right now instead of a backtest index."""
    factor = get_factor(factor_id)
    t = min(len(bars(s)) for s in UNIVERSE) - 1
    sig = signal_at(factor, t)
    ranked = sorted(UNIVERSE, key=lambda s: sig[s])
    shorts, longs = ranked[:HOLD], ranked[-HOLD:]
    return ([(s, 1, latest_price(s)) for s in longs]
            + [(s, -1, latest_price(s)) for s in shorts])


def _unrealized_return(positions: list[tuple[str, int, float]]) -> float:
    if not positions:
        return 0.0
    longs = [(s, p) for s, side, p in positions if side == 1]
    shorts = [(s, p) for s, side, p in positions if side == -1]
    long_ret = sum(latest_price(s) / p - 1 for s, p in longs) / max(1, len(longs))
    short_ret = sum(latest_price(s) / p - 1 for s, p in shorts) / max(1, len(shorts))
    return (long_ret - short_ret) / 2


def mark_to_market() -> dict[str, float]:
    """Recompute every engine's real forward-advancing NAV. Realizes the
    prior period's P&L into base_nav and opens fresh positions once per
    real calendar day; otherwise just marks currently-open positions at
    the freshest available real price."""
    if _db is None:
        return {}
    today = _today()
    now = int(time.time() * 1000)
    out: dict[str, float] = {}
    for engine, factor_id in ENGINE_FACTORS.items():
        base_nav, last_day = _get_state(engine)
        positions = _get_positions(engine)

        if last_day != today or not positions:
            if positions:
                base_nav *= 1 + _unrealized_return(positions)
            try:
                positions = _rank_latest(factor_id)
                _set_positions(engine, positions)
            except Exception as e:
                print(f"[aetherquant.paper] rebalance failed for {engine}: {e}")
                positions = []
            _set_state(engine, base_nav, today)

        nav = base_nav * (1 + _unrealized_return(positions))
        out[engine] = nav
        with _lock:
            _db.execute("INSERT INTO paper_nav VALUES (?, ?, ?)", [engine, now, nav])
    return out


def aggregate_nav() -> float | None:
    """Equal-weighted mean across the 5 paper books — the real replacement
    for the old replayed 'Aggregate Equity' NAV."""
    navs = mark_to_market()
    if not navs:
        return None
    return sum(navs.values()) / len(navs)
