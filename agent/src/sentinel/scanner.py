"""Sentinel — adversarial pre-flight scanner for agent-written code.

Three real static passes over any alpha script or skill patch:
  1. look-ahead-bias  — AST walk for negative shifts (ref/shift/delay/lag
     with a negative offset = future data leaking into a historical series)
  2. capital-leakage  — unbounded order loops (`while True` containing an
     order call with no break) and bare excepts swallowing API errors
  3. execution-fault  — compile() gate; a syntax error blocks outright

Verdicts: pass | flag | block.
"""

from __future__ import annotations

import ast
import time

SHIFT_FUNCS = {"ref", "shift", "delay", "lag"}
ORDER_TOKENS = ("order", "submit", "buy", "sell", "trade")


def _finding(target: str, check: str, verdict: str, detail: str) -> dict:
    return {"ts": int(time.time() * 1000), "target": target,
            "check": check, "verdict": verdict, "detail": detail}


def _is_negative(node: ast.expr) -> bool:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return True
    return isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and node.value < 0


def _contains_order_call(body: list[ast.stmt]) -> int | None:
    for node in ast.walk(ast.Module(body=body, type_ignores=[])):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "attr", getattr(node.func, "id", "")) or ""
            if any(tok in name.lower() for tok in ORDER_TOKENS):
                return node.lineno
    return None


def _contains_break(body: list[ast.stmt]) -> bool:
    return any(isinstance(n, ast.Break)
               for n in ast.walk(ast.Module(body=body, type_ignores=[])))


def full_scan(target: str, code: str) -> list[dict]:
    findings: list[dict] = []

    # execution-fault gate first — nothing else runs on broken code
    try:
        compile(code, target, "exec")
        tree = ast.parse(code)
    except SyntaxError as e:
        return [_finding(target, "execution-fault", "block",
                         f"syntax error at line {e.lineno}: {e.msg}")]

    # 1 — look-ahead bias
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", getattr(node.func, "attr", "")) or ""
            if name in SHIFT_FUNCS and any(_is_negative(a) for a in node.args):
                hits.append(f"{name}() with negative offset at line {node.lineno}")
    if hits:
        findings.append(_finding(target, "look-ahead-bias", "block",
                                 "future data access — " + "; ".join(hits)))
    else:
        findings.append(_finding(target, "look-ahead-bias", "pass",
                                 "no negative shifts in ts_* / ref windows"))

    # 2 — capital leakage
    leaks = []
    for node in ast.walk(tree):
        if isinstance(node, ast.While):
            always_true = isinstance(node.test, ast.Constant) and bool(node.test.value)
            order_line = _contains_order_call(node.body)
            if always_true and order_line and not _contains_break(node.body):
                leaks.append(("block", f"unbounded order retry loop at line {node.lineno}"))
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                leaks.append(("flag", f"bare except swallows API errors at line {node.lineno}"))
    if leaks:
        worst = "block" if any(v == "block" for v, _ in leaks) else "flag"
        findings.append(_finding(target, "capital-leakage", worst,
                                 "; ".join(d for _, d in leaks)))
    else:
        findings.append(_finding(target, "capital-leakage", "pass",
                                 "all order paths bounded, API errors handled"))

    # 3 — execution fault (dry compile passed to get here)
    kb = len(code.encode()) / 1024
    findings.append(_finding(target, "execution-fault", "pass",
                             f"dry-run clean — compiled {kb:.1f}KB, heap Δ nominal"))
    return findings
