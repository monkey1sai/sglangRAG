from __future__ import annotations

from typing import Callable, List, Tuple


def beam_search(
    candidates: List[str],
    scorer: Callable[[str], List[float]],
    beam_width: int,
    weights: List[float] | None = None,
) -> List[Tuple[str, List[float]]]:
    """Score candidates and return top-k by summed (or weighted) score."""
    scored = [(c, scorer(c)) for c in candidates]
    
    def calc_score(vec: List[float]) -> float:
        if weights:
            if len(weights) != len(vec):
                # Fallback to sum if dims mismatch
                return sum(vec)
            return sum(w * s for w, s in zip(weights, vec))
        return sum(vec)

    scored.sort(key=lambda x: calc_score(x[1]), reverse=True)
    return scored[:beam_width]
