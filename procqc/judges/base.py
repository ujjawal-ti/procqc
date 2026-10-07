"""What every per-kind check shares: the recording context and the routing of candidates.

Episode holds one recording, its task graph and the model clients. The narration and its step
sequence are computed on first use and reused by every check of the recording (the video call is
also cached on disk, so a re-run costs nothing).

Every check returns its candidates with a status:
  confirmed      the check is sure: a flag
  needs_review   the check is unsure: a human looks at it
  rejected       the check's verifier found the candidate wrong
`route` turns statuses into the three output lists. For kinds in ROUTE_REJECTED a verifier rejection
goes to human review instead of being dropped (the verifier there removes false candidates but also
some true ones; user decision, 6 Oct 2026). For the other kinds a rejection is dropped from the
flags and the review list, and stays visible in `candidates`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from procqc.graph.schema import TaskGraph

CONFIRMED, REVIEW, REJECTED = "confirmed", "needs_review", "rejected"
ROUTE_REJECTED = {"omission", "misordering"}


@dataclass
class Episode:
    graph: TaskGraph
    video_path: str
    gclient: Any                      # procqc.video_client.GenAIVideoClient
    text_client: Any                  # procqc.llm_client.LLMClient
    clip_dir: Path = Path("clips")
    episode_id: str = ""
    _duration: Optional[float] = field(default=None, repr=False)
    _narrated: Optional[tuple] = field(default=None, repr=False)

    @property
    def duration(self) -> float:
        if self._duration is None:
            from procqc.judges.narration import video_duration
            self._duration = video_duration(self.video_path)
        return self._duration

    def narrated(self) -> tuple:
        """(duration, narration with matches, performed step sequence), computed once."""
        if self._narrated is None:
            from procqc.judges.narration import narrated_sequence
            self._narrated = narrated_sequence(self.graph, self.video_path, self.gclient, self.text_client)
            self._duration = self._narrated[0]
        return self._narrated


def route(kind: str, candidates: List[dict]) -> Dict[str, List[dict]]:
    flags = [c for c in candidates if c.get("status") == CONFIRMED]
    review = [c for c in candidates if c.get("status") == REVIEW]
    if kind in ROUTE_REJECTED:
        for c in candidates:
            if c.get("status") == REJECTED:
                c["routed"] = "verifier rejected the candidate; a human decides"
                review.append(c)
    return {"flags": flags, "review": review}


def confidence_of(v: dict) -> float:
    """A verifier's self-reported confidence, 0.5 when missing."""
    try:
        return float(v.get("confidence", 0.5) or 0.5)
    except (TypeError, ValueError):
        return 0.5
