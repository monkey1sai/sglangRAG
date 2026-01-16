from __future__ import annotations

import multiprocessing as mp
from typing import Any, Dict, Tuple


SAFE_BUILTINS: Dict[str, Any] = {
    "len": len,
    "sum": sum,
    "min": min,
    "max": max,
    "float": float,
    "int": int,
    "str": str,
    "list": list,
    "dict": dict,
    "range": range,
    "abs": abs,
}


def _worker(code: str, text: str, ctx: Dict[str, Any], q: mp.Queue) -> None:
    """Execute scoring code in a restricted namespace.
    
    Security:
    - Uses a restricted `__builtins__` containing only safe pure functions.
    - No file I/O (no `open`).
    - No module imports (no `__import__`).
    - Runs in a separate process to isolate memory and allow timeout termination.
    """
    ns: Dict[str, Any] = {"__builtins__": SAFE_BUILTINS}
    exec(code, ns, ns)
    score_fn = ns.get("score")
    if not callable(score_fn):
        q.put(("error", "score() not found"))
        return
    q.put(("ok", score_fn(text, ctx)))


def run_scoring(code: str, text: str, ctx: Dict[str, Any], timeout_s: float) -> Tuple[bool, Any]:
    """Run scoring code with timeout; returns (ok, result_or_error)."""
    q: mp.Queue = mp.Queue()
    p = mp.Process(target=_worker, args=(code, text, ctx, q))
    p.start()
    p.join(timeout_s)
    if p.is_alive():
        p.terminate()
        return False, "timeout"
    if q.empty():
        return False, "no-result"
    status, payload = q.get()
    return (status == "ok"), payload
