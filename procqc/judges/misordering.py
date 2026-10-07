"""Misordering: candidates from the narrated step order and the procedure's dependencies (code), each
checked by one video call on the two moments involved.

Candidates (no model call). Walking the performed steps in time order, a step is misordered when one of
its direct required predecessors has not been performed yet AND is performed later. A predecessor that is
never performed is an omission, not a misordering. Only the first inverted step of each inversion is
reported: the missing predecessor is recorded as "owed", and later steps that need it are consequences.

Verifier (one video call, two clips), judged by object state. Each clip covers the claimed moment of a
step, padded by half the step's longest typical duration (graph `expected_duration_s`), within 5-45 s and
at most 120 s per clip:
  s_performed        is S performed (its result produced) in clip 1?
  r_result_during_s  when S is performed, is the result of its prerequisite R already present?
  r_result_later     by the end of clip 2, is R's result present?
  yes / no / yes, confidence >= 0.6           -> confirmed
  S not performed, or R's result already there -> rejected
  otherwise                                    -> needs_review
The verifier is a router: a rejection goes to human review, it is not dropped (`base.ROUTE_REJECTED`).
"""
from __future__ import annotations

from typing import List, Sequence, Tuple

from procqc import pricing, prompts
from procqc.graph import ops
from procqc.graph.schema import TaskGraph
from procqc.judges.base import CONFIRMED, REJECTED, REVIEW, Episode, confidence_of
from procqc.judges.narration import Step
from procqc.video_client import cut_clip

KIND = "misordering"
MIN_CONF = 0.6
PAD_MIN, PAD_MAX, CLIP_MAX = 5.0, 45.0, 120.0

VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "s_performed": {"type": "string", "enum": ["yes", "no", "unclear"]},
        "r_result_during_s": {"type": "string", "enum": ["yes", "no", "unclear"]},
        "r_result_later": {"type": "string", "enum": ["yes", "no", "unclear"]},
        "verdict": {"type": "string", "enum": ["misordered", "not_misordered", "unclear"]},
        "explanation": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["s_performed", "r_result_during_s", "r_result_later", "verdict", "explanation", "confidence"],
}


def find_misorderings(g: TaskGraph, seq: Sequence[Step]) -> List[dict]:
    done: set = set()
    owed: set = set()  # predecessors already reported as late: their dependents are consequences
    out: List[dict] = []
    for k, (idx, s, start, end, conf) in enumerate(seq):
        missing = [r for r in ops.required_predecessors(g, s) if r not in done]
        late = [r for r in missing if any(t == r for _, t, *_x in seq[k + 1:])]
        new = [r for r in late if r not in owed]
        if new:
            r = sorted(new)[0]
            j = next(j for j in range(k + 1, len(seq)) if seq[j][1] == r)
            _, _, rs, re_, rconf = seq[j]
            out.append({"kind": KIND, "step": s, "status": CONFIRMED, "confidence": round(min(conf, rconf), 3),
                        "start_s": start, "end_s": end, "span_s": [round(start, 2), round(end, 2)],
                        "prerequisite": r, "prerequisite_start_s": rs, "prerequisite_end_s": re_,
                        "entries": [idx, seq[j][0]],
                        "detail": f"{s} performed at {start:.1f}s before its prerequisite {r}, which is performed later "
                                  f"at {rs:.1f}s"})
            owed.update(late)
        done.add(s)
    return out


def pad(g: TaskGraph, step: str) -> float:
    d = g.node_map[step].expected_duration_s
    return max(PAD_MIN, min(PAD_MAX, 0.5 * float(d[1]))) if d else PAD_MIN


def windows(g: TaskGraph, f: dict, duration: float) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    ps, pr = pad(g, f["step"]), pad(g, f["prerequisite"])
    s0 = max(0.0, f["start_s"] - ps)
    s1 = min(duration, max(f["end_s"], f["start_s"] + 1.0) + ps, s0 + CLIP_MAX)
    r0 = max(0.0, f["prerequisite_start_s"] - pr)
    r1 = min(duration, max(f["prerequisite_end_s"], f["prerequisite_start_s"] + 1.0) + pr, r0 + CLIP_MAX)
    return (s0, s1), (r0, r1)


def verify(ep: Episode, f: dict) -> dict:
    g, nm = ep.graph, ep.graph.node_map
    (s0, s1), (r0, r1) = windows(g, f, ep.duration)
    with pricing.timed_stage("misorder_clips"):
        clips = [cut_clip(ep.video_path, s0, s1, ep.clip_dir), cut_clip(ep.video_path, r0, r1, ep.clip_dir)]
    S, R = nm[f["step"]], nm[f["prerequisite"]]
    user = (f"TASK: {g.name}. {(g.description or '').strip()}\n"
            f"STEP S: {S.description or S.name} (expected result: {S.effect_description or S.description})\n"
            f"STEP R, required before S: {R.description or R.name} (expected result: {R.effect_description or R.description})\n"
            f"Clip 1 covers {s0:.1f}-{s1:.1f} s of the video (detector: S at {f['start_s']:.1f}-{f['end_s']:.1f} s). "
            f"Clip 2 covers {r0:.1f}-{r1:.1f} s (detector: R at {f['prerequisite_start_s']:.1f}-{f['prerequisite_end_s']:.1f} s). "
            "Return the JSON.")
    with pricing.timed_stage("misorder_verify"):
        v = ep.gclient.ask(clips, prompts.get("misordering.verify.system"), user, VERIFY_SCHEMA, stage="misorder_verify")
    v = dict(v) if isinstance(v, dict) else {}
    v["clips_s"] = [[round(s0, 1), round(s1, 1)], [round(r0, 1), round(r1, 1)]]
    return v


def decide(f: dict, v: dict) -> str:
    s, during, later = (str(v.get(k, "unclear")).lower() for k in ("s_performed", "r_result_during_s", "r_result_later"))
    if s == "no" or during == "yes" or str(v.get("verdict")) == "not_misordered":
        return REJECTED
    if s == "yes" and during == "no" and later == "yes" and confidence_of(v) >= MIN_CONF:
        return CONFIRMED
    return REVIEW


def check(ep: Episode, verifier: bool = True) -> dict:
    _, _, seq = ep.narrated()
    with pricing.timed_stage("misorder_candidates"):
        cands = find_misorderings(ep.graph, seq)
    if verifier:
        for f in cands:
            f["verification"] = verify(ep, f)
            f["status"] = decide(f, f["verification"])
    return {"kind": KIND, "candidates": cands}


def oracle(g: TaskGraph, segments: Sequence[dict]) -> List[dict]:
    """The rule on a reference step sequence ([{start, end, label}]): its ceiling when the steps are right."""
    seq = [(i, s["label"], s["start"], s["end"], 1.0) for i, s in enumerate(sorted(segments, key=lambda x: x["start"]))]
    return find_misorderings(g, seq)

