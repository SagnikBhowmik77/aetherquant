"""Real cross-session memory — a DuckDB-backed key/value store (mirrors
market.py's `_open_db()` caching pattern), not an in-memory dict that
vanishes on restart and not a fabricated 'saved to memory/regimes.md' log
line with no file behind it."""

from __future__ import annotations

import threading
import time
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".cache" / "agent"
CACHE_DB = CACHE_DIR / "memory.duckdb"


def _open_db():
    import duckdb
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(CACHE_DB))
    con.execute("CREATE TABLE IF NOT EXISTS memory "
               "(key VARCHAR PRIMARY KEY, value VARCHAR, saved_at BIGINT)")
    return con


try:
    _db = _open_db()
except Exception as e:
    print(f"[aetherquant.memory] WARNING: duckdb unavailable ({e}) — memory tool disabled")
    _db = None

_lock = threading.Lock()


def remember(key: str, value: str) -> bool:
    if _db is None:
        return False
    with _lock:
        _db.execute("DELETE FROM memory WHERE key = ?", [key])
        _db.execute("INSERT INTO memory VALUES (?, ?, ?)", [key, value, int(time.time() * 1000)])
    return True


def recall(key: str) -> str | None:
    if _db is None:
        return None
    with _lock:
        row = _db.execute("SELECT value FROM memory WHERE key = ?", [key]).fetchone()
    return row[0] if row else None


def forget(key: str) -> bool:
    if _db is None:
        return False
    with _lock:
        _db.execute("DELETE FROM memory WHERE key = ?", [key])
    return True


def list_keys() -> list[str]:
    if _db is None:
        return []
    with _lock:
        rows = _db.execute("SELECT key FROM memory ORDER BY saved_at DESC").fetchall()
    return [r[0] for r in rows]
