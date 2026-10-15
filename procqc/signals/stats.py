"""Small scoring helpers shared by the signal checks."""
from __future__ import annotations

from typing import List, Optional


def auc(pos: List[float], neg: List[float]) -> Optional[float]:
    """Probability that a flagged recording scores higher than an unflagged one (ties count half)."""
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return round(wins / (len(pos) * len(neg)), 3)
