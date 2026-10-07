"""Early termination: compare the end of the recording with the procedure's final step.

One call per recording. The final moments (the last 10 % of the video, at least 20 s and at most 60 s)
are cut into a clip and sent as native video, so short final actions are not lost between sampled
frames. The model sees the clip, the required procedure steps numbered in the order they are performed,
the mandatory final step with its expected result, and the goal. No narration and no step matching.

It answers two questions: which required step is the LAST one performed in the final moments (from the
run of last actions it sees), and is the final step's result present at the end.

Decision (mutually exclusive with omission):
  last step seen is the final step                         -> no finding
  last step seen is an earlier step, result absent/unclear -> early_termination (confirmed at
                                                              confidence >= 0.6, else review)
  last step seen is an earlier step, result present        -> early_termination, needs_review
                                                              (sequence and end state disagree)
  no procedure step seen in the final moments              -> decided by the result: absent ->
                                                              confirmed, unclear -> needs_review,
                                                              present -> no finding
  If the final step is done but the goal is still not reached, a note says an earlier step is
  probably missing (an omission, judged by the omission check).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from procqc import pricing, prompts
from procqc.graph.schema import TaskGraph
from procqc.judges.base import CONFIRMED, REVIEW, Episode, confidence_of
from procqc.judges.narration import goal_text, step_dag
from procqc.video_client import cut_clip

KIND = "early_termination"
MIN_CONF = 0.6

SCHEMA = {
    "type": "object",
    "properties": {
        "final_actions": {"type": "array", "items": {"type": "string"}},
        "last_position": {"type": ["integer", "null"]},
        "final_step_result": {"type": "string", "enum": ["present", "absent", "unclear"]},
        "goal_state": {"type": "string", "enum": ["reached", "not_reached", "unclear"]},
        "end_state": {"type": "string"},
        "missing": {"type": "string"},
        "still_working": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["final_actions", "last_position", "final_step_result", "goal_state", "end_state", "missing",
                 "still_working", "confidence"],
}


def end_window(duration: float) -> tuple:
    """The final moments: the last 10 % of the video, at least 20 s and at most 60 s."""
    w = min(60.0, max(20.0, 0.10 * duration))
    return max(0.0, duration - w), duration


def required_sequence(g: TaskGraph) -> List[str]:
    """Required steps in the order they are performed, repeats included when the graph records the
    demonstrated sequence (metadata canonical_sequence); otherwise the topological order."""
    steps, _, order = step_dag(g)
    seq = (g.metadata or {}).get("canonical_sequence") or order
    return [s for s in seq if s in steps and not steps[s].optional]


def final_position(g: TaskGraph, seq: Sequence[str]) -> int:
    """1-based position of the last occurrence of the mandatory final step in the sequence."""
    term = {n.id for n in g.nodes if n.is_step and n.mandatory_terminal}
    pos = [i + 1 for i, s in enumerate(seq) if s in term]
    return pos[-1] if pos else len(seq)


def _ordinal(k: int) -> str:
    return {2: "2nd", 3: "3rd"}.get(k, f"{k}th")


def final_step_context(g: TaskGraph) -> str:
    steps, _, order = step_dag(g)
    term = [s for s in order if steps[s].mandatory_terminal] or order[-1:]
    L = [f"TASK: {g.name}", (g.description or "").strip(), ""]
    if g.objects:
        L.append("OBJECTS: " + "; ".join(o.name for o in g.objects))
    seq = required_sequence(g)
    fpos = final_position(g, seq)
    L.append("REQUIRED PROCEDURE STEPS, numbered by position in the order they are performed (optional steps "
             "omitted; a step done more than once appears at each position):")
    seen: Dict[str, int] = {}
    for i, s in enumerate(seq, 1):
        seen[s] = seen.get(s, 0) + 1
        n = steps[s]
        again = f" ({_ordinal(seen[s])} time)" if seen[s] > 1 else ""
        L.append(f"  {i}. {n.description or n.name}{again}" + ("   <- MANDATORY FINAL STEP" if i == fpos else ""))
    for s in term:
        n = steps[s]
        L.append("")
        L.append(f"FINAL STEP: {n.description or n.name}")
        L.append(f"  expected result: {n.effect_description or n.description or n.name}")
        if n.effects:
            L.append("  effects: " + "; ".join(str(p) for p in n.effects))
    goal = goal_text(g)
    if goal:
        L += ["", goal]
    return "\n".join(L)


def decide(g: TaskGraph, data: dict, duration: float) -> Optional[dict]:
    term = [n.id for n in g.nodes if n.is_step and n.mandatory_terminal]
    res = str(data.get("final_step_result", "unclear")).lower()
    conf = confidence_of(data)
    seq = required_sequence(g)
    fpos = final_position(g, seq)
    try:
        last = int(data.get("last_position"))
    except (TypeError, ValueError):
        last = None
    last = last if last is not None and 1 <= last <= len(seq) else None
    if last is not None and last >= fpos:
        return None
    if last is not None:
        status = CONFIRMED if (res == "absent" and conf >= MIN_CONF) else REVIEW
        why = (f"the last step performed is position {last} ({seq[last - 1]}), before the final step at {fpos}; "
               f"final step result {res}" + (" (sequence and end state disagree)" if res == "present" else ""))
    else:
        if res == "present":
            return None
        status = CONFIRMED if (res == "absent" and conf >= MIN_CONF) else REVIEW
        why = f"no procedure step in the final moments; final step result {res}"
    return {"kind": KIND, "status": status, "step": term[0] if term else None, "confidence": conf,
            "span_s": [round(duration, 2), round(duration, 2)], "detail": f"{why}: {data.get('missing', '')}"[:400]}


def check(ep: Episode) -> dict:
    g, duration = ep.graph, ep.duration
    a, b = end_window(duration)
    with pricing.timed_stage("termination_clip"):
        clip = cut_clip(ep.video_path, a, b, ep.clip_dir)
    user = (final_step_context(g) + f"\n\nThe clip shows the final moments of the recording: clip time 0 s is "
            f"{a:.1f} s of the video and the clip ends at the video's end ({duration:.1f} s). Return the JSON.")
    with pricing.timed_stage("termination_check"):
        data = ep.gclient.ask(clip, prompts.get("termination.check.system"), user, SCHEMA, stage="termination_check")
    data = data if isinstance(data, dict) else {}
    finding = decide(g, data, duration)
    if finding is None and str(data.get("goal_state", "")).lower() == "not_reached":
        data["note"] = "final step done but the goal is not reached: an earlier step is probably missing (omission)"
    return {"kind": KIND, "candidates": [finding] if finding else [], "judgement": data,
            "window_s": [round(a, 2), round(b, 2)]}
