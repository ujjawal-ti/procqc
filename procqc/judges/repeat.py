"""Redundant repetition: candidates by counting performances per step in the narrated step sequence
(code), each checked by one repeat-specific video call.

A redundant repeat is a step performed again after its result was already achieved, beyond the number
of times the procedure allows (`permitted_repeats`; steps inside a version 2 repeat block are unbounded),
with nothing in between that made the redo needed. Not a repeat: a correction (something went wrong,
undo and redo), a redo because the object changed in between, strokes inside one continuous action, a
step allowed several times within its count.

Candidates (no model call). A performance is one narration entry matched to the step; an entry that
continues the previous one (`continues_entry`) is the same performance. Every performance beyond
`permitted_repeats` is a candidate, with the previous performance as context. A repeat of a step whose
text states an amount (a count of units) is the wrong amount: it is reported as a parameter deviation
tagged `repeated_addition` (`route`). Durations are not amounts.

Verifier (one video call, two clips: the previous performance and the candidate one, each padded 2 s, at
most 45 s):
  same_step_again          is the step performed again, on the same object, in clip 2?
  first_result_achieved    at the end of clip 1, was the step's result achieved?
  went_wrong               did the first performance fail or get undone?
  object_changed           did the object change in between, so the result had to be redone?
  redundant_repeat, same yes, first yes, wrong no, changed no, confidence >= 0.6  -> confirmed
  correction (noted), needed_redo, not_a_repeat, or same_step_again no            -> rejected
  otherwise                                                                       -> needs_review
"""
from __future__ import annotations

import re
from typing import Dict, List, Sequence

from procqc import pricing, prompts
from procqc.graph.schema import TaskGraph
from procqc.judges.base import CONFIRMED, REJECTED, REVIEW, Episode, confidence_of
from procqc.video_client import cut_clip

KIND = "addition_repeat"
MIN_CONF = 0.6
PAD, MAX_CLIP = 2.0, 45.0

# An amount: a number (digits, a fraction, or a number word) followed by a unit or a noun. Time units are
# excluded (a duration is not an amount), and so are references to step numbers.
_NUMBER = r"(?:\d+(?:[.,]\d+)?(?:\s*/\s*\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|half|a\s+single)"
_TIME = r"(?:s|sec|secs|seconds?|min|mins|minutes?|h|hrs?|hours?|times?)\b"
_AMOUNT = re.compile(rf"(?<![\w/.])(?<!step )(?<!steps ){_NUMBER}\s+(?!{_TIME})[a-z]", re.I)


def is_amount_step(node) -> bool:
    return bool(_AMOUNT.search(node.description or node.name or ""))


def route(g: TaskGraph, f: dict) -> dict:
    """Which kind reports the candidate: redundant repeat, or parameter deviation (repeated addition)."""
    if is_amount_step(g.node_map[f["step"]]):
        f["report_as"], f["tag"] = "parameter_deviation", "repeated_addition"
    else:
        f["report_as"], f["tag"] = KIND, None
    return f


def performances(narr: dict, step_ids: set) -> List[tuple]:
    """[(entry index, step id, start_s, end_s)] with continuing entries folded into the one they continue."""
    acts = narr.get("actions", []) or []
    out: List[tuple] = []
    for i, a in enumerate(acts):
        sids = a.get("matched_step_ids")
        if sids is None:
            sids = [a.get("matched_step_id")] if a.get("matched_step_id") else []
        sids = [s for s in sids if s in step_ids]
        cont = a.get("continues_entry")
        if cont is not None and out and out[-1][0] == cont and out[-1][1] in sids:
            k, s, st, _ = out[-1]
            out[-1] = (k, s, st, float(a.get("end_s", 0)))
            continue
        for s in sids:
            out.append((i, s, float(a.get("start_s", 0)), float(a.get("end_s", 0))))
    return out


def find_repeats(g: TaskGraph, perf: Sequence[tuple]) -> List[dict]:
    nm = g.node_map
    seen: Dict[str, List[tuple]] = {}
    out = []
    for p in perf:
        prev = seen.setdefault(p[1], [])
        if len(prev) >= nm[p[1]].permitted_repeats:
            q = prev[-1]
            out.append({"kind": KIND, "step": p[1], "status": CONFIRMED, "confidence": 1.0,
                        "entry": p[0], "span_s": [round(p[2], 2), round(p[3], 2)],
                        "previous_entry": q[0], "previous_s": [round(q[2], 2), round(q[3], 2)],
                        "occurrence": len(prev) + 1, "allowed": nm[p[1]].permitted_repeats,
                        "adjacent": p[0] - q[0] <= 1,
                        "detail": f"{p[1]} performed {len(prev) + 1} times (allowed {nm[p[1]].permitted_repeats}); "
                                  f"previous at {q[2]:.1f}s"})
        prev.append(p)
    return out


VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        **{k: {"type": "string", "enum": ["yes", "no", "unclear"]}
           for k in ("same_step_again", "first_result_achieved", "went_wrong", "object_changed")},
        "verdict": {"type": "string", "enum": ["redundant_repeat", "correction", "needed_redo", "not_a_repeat", "unclear"]},
        "explanation": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["same_step_again", "first_result_achieved", "went_wrong", "object_changed", "verdict",
                 "explanation", "confidence"],
}


def clip_windows(f: dict, duration: float) -> List[List[float]]:
    W = []
    for s, e in (f["previous_s"], f["span_s"]):
        a, b = max(0.0, s - PAD), min(duration, e + PAD)
        if b - a < 3.0:
            b = min(duration, a + 3.0)
        W.append([a, min(b, a + MAX_CLIP)])
    return W


def verify(ep: Episode, f: dict) -> dict:
    g = ep.graph
    X = g.node_map[f["step"]]
    W = clip_windows(f, ep.duration)
    with pricing.timed_stage("repeat_clips"):
        clips = [cut_clip(ep.video_path, a, b, ep.clip_dir) for a, b in W]
    allowed = "once" if f["allowed"] == 1 else f"up to {f['allowed']} times"
    user = (f"TASK: {g.name}. {(g.description or '').strip()}\n"
            f"STEP X: {X.description or X.name} (expected result: {X.effect_description or X.description}); "
            f"the procedure allows it {allowed}.\n"
            f"Clip 1 covers {W[0][0]:.1f}-{W[0][1]:.1f} s (earlier performance at about {f['previous_s'][0]:.1f}-"
            f"{f['previous_s'][1]:.1f} s); clip 2 covers {W[1][0]:.1f}-{W[1][1]:.1f} s (claimed repeat at about "
            f"{f['span_s'][0]:.1f}-{f['span_s'][1]:.1f} s). Return the JSON.")
    with pricing.timed_stage("repeat_verify"):
        v = ep.gclient.ask(clips, prompts.get("repeat.verify.system"), user, VERIFY_SCHEMA, stage="repeat_verify")
    v = dict(v) if isinstance(v, dict) else {}
    v["clips_s"] = [[round(a, 1), round(b, 1)] for a, b in W]
    return v


def decide(f: dict, v: dict) -> str:
    same, first, wrong, changed, verdict = (str(v.get(k, "unclear")).lower() for k in
                                            ("same_step_again", "first_result_achieved", "went_wrong",
                                             "object_changed", "verdict"))
    if verdict == "correction":
        f["note"] = "correction"
        return REJECTED
    if verdict in ("needed_redo", "not_a_repeat") or same == "no":
        return REJECTED
    if verdict == "redundant_repeat" and same == "yes" and first == "yes" and wrong == "no" and changed == "no" \
            and confidence_of(v) >= MIN_CONF:
        return CONFIRMED
    return REVIEW


def check(ep: Episode, verifier: bool = True) -> dict:
    g = ep.graph
    _, narr, _ = ep.narrated()
    with pricing.timed_stage("repeat_candidates"):
        cands = [route(g, f) for f in find_repeats(g, performances(narr, {n.id for n in g.nodes if n.is_step}))]
    if verifier:
        for f in cands:
            f["verification"] = verify(ep, f)
            f["status"] = decide(f, f["verification"])
    return {"kind": KIND, "candidates": cands}
