"""Omission: candidates from the narrated step sequence and the graph (code), each checked by one
omission-specific video call.

Candidates (no model call). A required (non-optional, unconditional) step is a candidate when it is never
performed in the narrated sequence while a step that requires it, directly or through other steps, IS
performed. A mandatory final step that is never performed belongs to early termination, and a missing step
with nothing after it performed is an unfinished tail, also early termination. The expected window is the
gap between the last performed step it requires and the first performed step that requires it.

Verifier (one video call, three clips): the gap where the step belongs (at most the last 120 s before the
dependent step), the start of the first dependent step, and the first 15 s of the recording. Questions by
object state:
  performed_in_gap         is the step performed (its result produced) in clip 1?
  result_before_dependent  at the start of clip 2, is the step's result present?
  present_at_start         in clip 3, is the result already present (pre-satisfied)?
  no / no / no, confidence >= 0.6  -> confirmed
  performed, or result present     -> rejected (a result present without the action seen is noted as
                                      `offcamera_or_presatisfied`)
  otherwise                        -> needs_review
The verifier is a router: a rejection goes to human review, it is not dropped (`base.ROUTE_REJECTED`).
"""
from __future__ import annotations

from typing import Dict, List, Sequence

from procqc import pricing, prompts
from procqc.graph import ops
from procqc.graph.schema import TaskGraph
from procqc.judges.base import CONFIRMED, REJECTED, REVIEW, Episode, confidence_of
from procqc.video_client import cut_clip

KIND = "omission"
MIN_CONF = 0.6
GAP_MAX, DEP_PAD, START_CLIP = 120.0, 15.0, 15.0

VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "performed_in_gap": {"type": "string", "enum": ["yes", "no", "unclear"]},
        "result_before_dependent": {"type": "string", "enum": ["yes", "no", "unclear"]},
        "present_at_start": {"type": "string", "enum": ["yes", "no", "unclear"]},
        "verdict": {"type": "string", "enum": ["omitted", "not_omitted", "unclear"]},
        "explanation": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["performed_in_gap", "result_before_dependent", "present_at_start", "verdict", "explanation",
                 "confidence"],
}


def find_omissions(g: TaskGraph, seq: Sequence[tuple]) -> List[dict]:
    """seq: [(entry index, step id, start_s, end_s, confidence), ...] in time order."""
    nm = g.node_map
    performed: Dict[str, List[tuple]] = {}
    for x in seq:
        performed.setdefault(x[1], []).append(x)
    out = []
    for s in (n.id for n in g.nodes if n.is_step):
        n = nm[s]
        if s in performed or n.optional or n.conditional_on is not None or n.mandatory_terminal:
            continue
        deps = [d for d in ops.descendants(g, s) if d in performed]
        if not deps:
            continue  # nothing after it was done: an unfinished tail, judged as early termination
        preds = ops.transitive_required_predecessors(g, s)
        lo = max([e for p in preds if p in performed for (_, _, _, e, _) in performed[p]] or [0.0])
        first_dep = min((performed[d][0] for d in deps), key=lambda x: x[2])
        hi = first_dep[2]
        if hi < lo:  # dependent narrated before the prerequisites: use the dependent's run-up
            lo = max(0.0, hi - GAP_MAX)
        out.append({"kind": KIND, "step": s, "status": CONFIRMED, "confidence": 1.0,
                    "gap_s": [round(lo, 2), round(hi, 2)], "span_s": [round(lo, 2), round(hi, 2)],
                    "dependent": first_dep[1],
                    "dependent_s": [round(first_dep[2], 2), round(first_dep[3], 2)],
                    "detail": f"{s} is never performed, but {first_dep[1]}, which requires it, is performed at "
                              f"{first_dep[2]:.1f}s"})
    return out


def clip_windows(f: dict, duration: float) -> List[List[float]]:
    lo, hi = f["gap_s"]
    lo = max(lo - 3.0, hi - GAP_MAX, 0.0)
    gap = [lo, min(duration, max(hi + 3.0, lo + 4.0))]
    ds = f["dependent_s"][0]
    dep = [max(0.0, ds - 3.0), min(duration, ds + DEP_PAD)]
    start = [0.0, min(duration, START_CLIP)]
    return [gap, dep, start]


def verify(ep: Episode, f: dict) -> dict:
    g, nm = ep.graph, ep.graph.node_map
    W = clip_windows(f, ep.duration)
    with pricing.timed_stage("omission_clips"):
        clips = [cut_clip(ep.video_path, a, b, ep.clip_dir) for a, b in W]
    X, D = nm[f["step"]], nm[f["dependent"]]
    user = (f"TASK: {g.name}. {(g.description or '').strip()}\n"
            f"STEP X (claimed omitted): {X.description or X.name} (expected result: {X.effect_description or X.description})\n"
            f"STEP D (requires X, performed): {D.description or D.name}\n"
            f"Clip 1 covers {W[0][0]:.1f}-{W[0][1]:.1f} s, clip 2 covers {W[1][0]:.1f}-{W[1][1]:.1f} s (D starts at about "
            f"{f['dependent_s'][0]:.1f} s), clip 3 covers {W[2][0]:.1f}-{W[2][1]:.1f} s. Return the JSON.")
    with pricing.timed_stage("omission_verify"):
        v = ep.gclient.ask(clips, prompts.get("omission.verify.system"), user, VERIFY_SCHEMA, stage="omission_verify")
    v = dict(v) if isinstance(v, dict) else {}
    v["clips_s"] = [[round(a, 1), round(b, 1)] for a, b in W]
    return v


def decide(f: dict, v: dict) -> str:
    gap, before, start = (str(v.get(k, "unclear")).lower() for k in
                          ("performed_in_gap", "result_before_dependent", "present_at_start"))
    if gap == "yes" or before == "yes" or start == "yes" or str(v.get("verdict")) == "not_omitted":
        if gap != "yes" and (before == "yes" or start == "yes"):
            f["note"] = "offcamera_or_presatisfied"
        return REJECTED
    if gap == "no" and before == "no" and start != "yes" and confidence_of(v) >= MIN_CONF:
        return CONFIRMED
    return REVIEW


def check(ep: Episode, verifier: bool = True) -> dict:
    _, _, seq = ep.narrated()
    with pricing.timed_stage("omission_candidates"):
        cands = find_omissions(ep.graph, seq)
    if verifier:
        for f in cands:
            f["verification"] = verify(ep, f)
            f["status"] = decide(f, f["verification"])
    return {"kind": KIND, "candidates": cands}
