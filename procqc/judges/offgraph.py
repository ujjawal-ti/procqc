"""Off-graph addition: candidates from the narration (one text call that gives every unmatched entry a
role), each checked by one addition-specific video call.

An off-graph addition is a self-contained action that is no step of the procedure and serves none.
Supporting work is not an addition: getting an object a step uses ready, putting a step's things away,
cleaning up after a step, adjusting the current step's object in place, consulting the instructions.

Candidates. Entries the narrator marked `scene_change` are candidates directly. Every other entry with no
matched step gets a role from one text call (prepare, tidy, adjust, instructions, transition, unrelated);
entries with role `unrelated` are candidates. Consecutive candidate entries (gap <= 2 s) merge into one.

Verifier (one video call, two clips): the candidate span (padded 2 s, at least 4 s, at most 60 s) and an
8 s reference of the main task just before it (after it, at the very start). Questions:
  same_setting       is clip 1 in the same place as clip 2?
  serves_procedure   does the action perform, prepare, tidy after or adjust a listed step?
  verdict            addition / not_addition / unclear
  addition, and (serves no step or a different setting), confidence >= 0.6   -> confirmed
  serves a step, or verdict not_addition                                       -> rejected
  otherwise                                                                    -> needs_review
"""
from __future__ import annotations

from typing import Dict, List, Optional

from procqc import pricing, prompts
from procqc.graph.schema import TaskGraph
from procqc.judges.base import CONFIRMED, REJECTED, REVIEW, Episode, confidence_of
from procqc.judges.narration import MATCH_REASONING_EFFORT, graph_context, narration_text
from procqc.video_client import cut_clip

KIND = "addition_offgraph"
MIN_CONF = 0.6
MERGE_GAP, PAD, MIN_CLIP, MAX_CLIP, REF_LEN = 2.0, 2.0, 4.0, 60.0, 8.0
ROLES = ("prepare", "tidy", "adjust", "instructions", "transition", "unrelated")

ROLE_SCHEMA = {
    "type": "object",
    "properties": {
        "entries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "role": {"type": "string", "enum": list(ROLES)},
                    "serves_step": {"type": ["string", "null"]},
                    "reason": {"type": "string"},
                },
                "required": ["index", "role", "serves_step", "reason"],
            },
        },
    },
    "required": ["entries"],
}

VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "action_seen": {"type": "string"},
        "same_setting": {"type": "string", "enum": ["yes", "no", "unclear"]},
        "serves_procedure": {"type": "string", "enum": ["yes", "no", "unclear"]},
        "served_step": {"type": ["string", "null"]},
        "verdict": {"type": "string", "enum": ["addition", "not_addition", "unclear"]},
        "explanation": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["action_seen", "same_setting", "serves_procedure", "served_step", "verdict", "explanation",
                 "confidence"],
}


def unmatched(narr: dict) -> List[int]:
    return [i for i, a in enumerate(narr.get("actions", []) or [])
            if not a.get("matched_step_ids") and not a.get("matched_step_id") and not a.get("scene_change")]


def classify_roles(g: TaskGraph, narr: dict, text_client, text_model: Optional[str] = None) -> Dict[int, dict]:
    """One text call: a role for every unmatched entry that is not a scene change."""
    idx = unmatched(narr)
    if not idx:
        return {}
    ctx, _ = graph_context(g)
    user = (f"=== PROCEDURE ===\n{ctx}\n\n=== NARRATION (with matched steps) ===\n{narration_text(narr)}\n\n"
            f"=== ENTRIES TO CLASSIFY ===\n{', '.join(f'#{i}' for i in idx)}\n\nReturn one role per listed entry, by index.")
    with pricing.timed_stage("offgraph_roles"):
        data = text_client.complete_json(prompts.get("offgraph.roles.system"), user, schema=ROLE_SCHEMA,
                                         schema_name="roles", model=text_model, max_tokens=12000,
                                         reasoning_effort=MATCH_REASONING_EFFORT)
    out = {}
    for e in (data.get("entries") or [] if isinstance(data, dict) else []):
        try:
            i = int(e.get("index"))
        except (TypeError, ValueError):
            continue
        if i in idx:
            role = str(e.get("role", "")).lower()
            out[i] = {"role": role if role in ROLES else "unclear", "serves_step": e.get("serves_step"),
                      "reason": str(e.get("reason", ""))[:120]}
    return out


def find_additions(narr: dict, roles: Dict[int, dict]) -> List[dict]:
    """Candidate spans: scene-change entries and entries with role `unrelated`, consecutive ones merged."""
    acts = narr.get("actions", []) or []
    hits = []
    for i, a in enumerate(acts):
        src = "scene_change" if a.get("scene_change") else ("unrelated" if (roles.get(i) or {}).get("role") == "unrelated"
                                                             else None)
        if src:
            hits.append((i, src, float(a.get("start_s", 0)), float(a.get("end_s", 0))))
    out: List[dict] = []
    for i, src, s, e in hits:
        if out and s - out[-1]["span_s"][1] <= MERGE_GAP and out[-1]["entries"][-1] == i - 1:
            c = out[-1]
            c["entries"].append(i)
            c["span_s"][1] = max(c["span_s"][1], e)
            if src not in c["sources"]:
                c["sources"].append(src)
            continue
        out.append({"kind": KIND, "step": None, "status": CONFIRMED, "confidence": 1.0,
                    "entries": [i], "sources": [src], "span_s": [s, e]})
    for c in out:
        c["span_s"] = [round(c["span_s"][0], 2), round(c["span_s"][1], 2)]
        c["detail"] = "; ".join(f"#{i} {acts[i].get('verb', '')} {acts[i].get('object', '')} ({acts[i].get('state_change', '')})"
                                for i in c["entries"])[:400]
        c["reason"] = "; ".join((roles.get(i) or {}).get("reason", "scene change") for i in c["entries"])[:200]
    return out


def clip_windows(f: dict, duration: float) -> List[List[float]]:
    s, e = f["span_s"]
    a, b = max(0.0, s - PAD), min(duration, e + PAD)
    if b - a < MIN_CLIP:
        mid = (a + b) / 2
        a, b = max(0.0, mid - MIN_CLIP / 2), min(duration, mid + MIN_CLIP / 2)
    b = min(b, a + MAX_CLIP)
    if a >= REF_LEN + 1.0:
        ref = [a - 1.0 - REF_LEN, a - 1.0]
    else:  # candidate at the very start: take the reference after it
        ref = [min(duration, b + 1.0), min(duration, b + 1.0 + REF_LEN)]
    return [[a, b], ref]


def step_list(g: TaskGraph) -> str:
    return "\n".join(f"  [{n.id}] {n.description or n.name}" for n in g.nodes if n.is_step)


def verify(ep: Episode, f: dict) -> dict:
    g = ep.graph
    W = clip_windows(f, ep.duration)
    with pricing.timed_stage("offgraph_clips"):
        clips = [cut_clip(ep.video_path, a, b, ep.clip_dir) for a, b in W if b - a >= 1.0]
    objs = "; ".join(o.name for o in g.objects) if g.objects else "(not listed)"
    user = (f"TASK: {g.name}. {(g.description or '').strip()}\nOBJECTS: {objs}\nPROCEDURE STEPS:\n{step_list(g)}\n\n"
            f"Clip 1 covers {W[0][0]:.1f}-{W[0][1]:.1f} s (the suspected addition, about "
            f"{f['span_s'][0]:.1f}-{f['span_s'][1]:.1f} s)."
            + (f" Clip 2 covers {W[1][0]:.1f}-{W[1][1]:.1f} s (reference)." if len(clips) > 1 else " There is no reference clip.")
            + " Return the JSON.")
    with pricing.timed_stage("offgraph_verify"):
        v = ep.gclient.ask(clips, prompts.get("offgraph.verify.system"), user, VERIFY_SCHEMA, stage="offgraph_verify")
    v = dict(v) if isinstance(v, dict) else {}
    v["clips_s"] = [[round(a, 1), round(b, 1)] for a, b in W]
    return v


def decide(f: dict, v: dict) -> str:
    same, serves, verdict = (str(v.get(k, "unclear")).lower() for k in ("same_setting", "serves_procedure", "verdict"))
    if verdict == "addition" and (serves == "no" or same == "no") and confidence_of(v) >= MIN_CONF:
        return CONFIRMED
    if verdict == "not_addition" or (serves == "yes" and same != "no"):
        return REJECTED
    return REVIEW


def check(ep: Episode, verifier: bool = True) -> dict:
    _, narr, _ = ep.narrated()
    roles = classify_roles(ep.graph, narr, ep.text_client)
    with pricing.timed_stage("offgraph_candidates"):
        cands = find_additions(narr, roles)
    if verifier:
        for f in cands:
            f["verification"] = verify(ep, f)
            f["status"] = decide(f, f["verification"])
    return {"kind": KIND, "candidates": cands, "roles": {str(k): v for k, v in roles.items()}}
