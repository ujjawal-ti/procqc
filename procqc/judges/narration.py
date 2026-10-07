"""The shared narration and step-matching stage.

NARRATE (one native-video call, Google AI Studio)
    An observer writes a timestamped list of every distinct manipulation in the video: hand, verb, object,
    source, destination, resulting state change, count, and whether the surroundings changed. The
    narrator sees the task, its objects and the step texts as an alphabetical vocabulary, with no ids and
    no order, so the narration is not pulled towards the written sequence. It also reports the scene at
    the start and the state of the objects at the end. The answer is cached, so every check that reads
    the narration shares one call per video.

MATCH (one text call, Fuelix)
    Assigns each entry to the step(s) it performs, by content, with look-alike candidates;
    `resolve_lookalikes` then applies the identity convention (IDENTITY_CONVENTION) deterministically.

`narrated_sequence` runs both and returns the performed step sequence the per-kind checks start from.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from procqc import pricing, prompts
from procqc.graph import ops
from procqc.graph.schema import TaskGraph

# How an observed action is assigned to one of several look-alike steps (the same action on the same
# object at several points of the procedure) when its content does not tell them apart:
#   "position": the latest look-alike step whose required steps are all done at that moment; the
#               natural convention for a checker that walks the procedure.
#   "content":  keep the matcher's first choice (closest step text: amount, duration, setting).
IDENTITY_CONVENTION = "position"

# matching by content is a lookup, not a judgement; unbounded reasoning made it the slowest stage
MATCH_REASONING_EFFORT = "low"

# Transport and handling verbs: steps that share one of these are told apart by their object, so they
# are not look-alikes. Generic English, not tied to a task or domain.
_GENERIC_VERBS = {"pick", "place", "put", "take", "add", "grab", "lift", "remove", "move", "open", "close", "get",
                  "set", "hold", "bring", "return", "insert", "drop", "throw", "pour"}
_CONTINUE_VERBS = {"continue", "keep", "repeat", "resume"}

IDENTITY_RULE = {
    "position": (
        "When an action could be any step of a look-alike group and its object, amount or setting does not tell "
        "them apart, it is the LATEST step of the group (in procedure order) whose required steps have all been "
        "performed at that moment; an earlier step of the group that never got an action is then the missing one. "
        "A difference in amount or duration from the step text does not change which step it is; it is a "
        "parameter deviation of that step."),
    "content": (
        "When an action could be any step of a look-alike group, it is the step whose text matches the observed "
        "object, amount, duration or setting most closely."),
}


def _action_word(desc: str) -> str:
    """Main action of a step text: the head verb, or the verb after 'continue to' / 'keep'."""
    w = re.sub(r"[^a-z ]", " ", desc.lower()).split()
    if not w:
        return ""
    if w[0] in _CONTINUE_VERBS and len(w) > 1:
        rest = w[2:] if w[1] == "to" else w[1:]
        return rest[0] if rest else w[0]
    return w[0]


def lookalike_groups(g: TaskGraph, order: Sequence[str]) -> List[List[str]]:
    """Groups of 2+ steps that share a specific (non-transport) action word, in procedure order."""
    by: Dict[str, List[str]] = {}
    nm = g.node_map
    for sid in order:
        a = _action_word(nm[sid].description or nm[sid].name)
        if a and a not in _GENERIC_VERBS:
            by.setdefault(a, []).append(sid)
    return [v for v in by.values() if len(v) >= 2]


def step_dag(g: TaskGraph):
    """(steps by id, prerequisite DAG over steps, a topological order)."""
    import networkx as nx
    steps = {n.id: n for n in g.nodes if n.is_step}
    dag = nx.DiGraph()
    dag.add_nodes_from(steps)
    for e in g.edges:
        rel = str(getattr(e.relation, "value", e.relation)).upper()
        if e.source in steps and e.target in steps and rel != "CORRECTS":
            dag.add_edge(e.source, e.target)
    try:
        order = list(nx.lexicographical_topological_sort(dag))
    except nx.NetworkXUnfeasible:
        order = list(steps)
    return steps, dag, order


def goal_text(g: TaskGraph) -> str:
    if g.goal:
        return "GOAL STATE (must be true at the end): " + "; ".join(str(p) for p in g.goal)
    term = [n for n in g.nodes if n.is_step and n.mandatory_terminal]
    if term:
        return ("GOAL (no explicit goal state is given; the task is complete when the mandatory final step's result "
                "is present at the end): " + "; ".join(n.effect_description or n.description or n.name for n in term))
    return ""


def graph_context(g: TaskGraph, convention: str = IDENTITY_CONVENTION) -> Tuple[str, List[str]]:
    """Everything the graph knows, in one block of text. Returns (text, step ids in topological order)."""
    steps, dag, order = step_dag(g)
    pos = {n: i + 1 for i, n in enumerate(order)}
    is_chain = all(dag.in_degree(n) <= 1 and dag.out_degree(n) <= 1 for n in order)
    L = [f"TASK: {g.name}", (g.description or "").strip(), ""]
    if g.objects:
        L.append("OBJECTS (id: name [category]; aliases):")
        for o in g.objects:
            al = ", ".join(getattr(o, "aliases", []) or [])
            L.append(f"  {o.id}: {o.name} [{getattr(o, 'category', '')}]" + (f"; also called {al}" if al else ""))
        L.append("")
    if g.initial_state:
        L.append("INITIAL STATE (true at the start): " + "; ".join(str(p) for p in g.initial_state))
    goal = goal_text(g)
    if goal:
        L.append(goal)
    if g.initial_state or goal:
        L.append("")
    L.append("PROCEDURE STEPS in a valid order. " + (
        "This procedure is a strict chain: every step requires the previous one."
        if is_chain else
        "Each step lists the steps it REQUIRES. Steps with no dependency path between them may be done in "
        "either order; that is not an error."))
    for n_id in order:
        n = steps[n_id]
        bits = []
        reqs = sorted(dag.predecessors(n_id), key=lambda x: pos[x])
        bits.append("requires " + (", ".join(f"step {pos[r]}" for r in reqs) if reqs else "nothing"))
        if n.optional:
            bits.append("OPTIONAL: may be skipped; skipping it is never an error")
        if n.permitted_repeats > 1:
            bits.append(f"may be performed up to {n.permitted_repeats} times")
        else:
            bits.append("performed once")
        if n.mandatory_terminal:
            bits.append("MANDATORY FINAL STEP")
        if n.expected_duration_s:
            lo, hi = n.expected_duration_s
            bits.append(f"typically {lo:.0f}-{hi:.0f} s")
        L.append(f"  step {pos[n_id]}  [{n.id}]  {n.description or n.name}")
        L.append("      " + "; ".join(bits))
        if n.preconditions:
            L.append("      preconditions: " + "; ".join(str(p) for p in n.preconditions))
        if n.effects:
            L.append("      effects: " + "; ".join(str(p) for p in n.effects))
        if n.effect_description:
            L.append("      expected result: " + n.effect_description)
        if n.start_rule:
            L.append("      starts when: " + n.start_rule)
        if n.end_rule:
            L.append("      ends when: " + n.end_rule)
        if n.pitfalls:
            L.append("      known pitfalls: " + "; ".join(n.pitfalls))
        if n.allowed_substitutes:
            L.append("      allowed substitutes: " + json.dumps(n.allowed_substitutes))
    groups = lookalike_groups(g, order)
    if groups:
        L += ["", "LOOK-ALIKE STEPS (the same kind of action appears as several steps):"]
        for grp in groups:
            L.append("  " + "; ".join(
                f"step {pos[s]} [{s}] requires " + (", ".join(f"step {pos[r]}" for r in sorted(dag.predecessors(s), key=lambda x: pos[x])) or "nothing")
                for s in grp))
        L.append("  Identity rule: " + IDENTITY_RULE[convention])
    return "\n".join(L), order


# ------------------------------------------------------------------------------------------
# narrate
# ------------------------------------------------------------------------------------------
NARRATE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "scene_start": {"type": "string", "description": "objects visible at the start and their states"},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_s": {"type": "number"},
                    "end_s": {"type": "number"},
                    "hand": {"type": "string"},
                    "verb": {"type": "string"},
                    "object": {"type": "string"},
                    "from_location": {"type": ["string", "null"]},
                    "to_location": {"type": ["string", "null"]},
                    "state_change": {"type": "string", "description": "explicit before -> after of the affected object(s), or 'no change'"},
                    "quantity_or_setting": {"type": ["string", "null"]},
                    "count": {"type": "integer"},
                    "scene_change": {"type": "boolean"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["start_s", "end_s", "hand", "verb", "object", "from_location", "to_location",
                             "state_change", "quantity_or_setting", "count", "scene_change", "confidence"],
            },
        },
        "scene_end": {"type": "string", "description": "state of the task objects at the end; is the person still working?"},
        "notes": {"type": "string", "description": "occlusions, uncertain moments, anything the camera did not show"},
    },
    "required": ["scene_start", "actions", "scene_end", "notes"],
}


def narrator_context(g: TaskGraph) -> str:
    """What the narrator may know: task, objects, and the step texts as an unordered vocabulary.
    No step ids and no order, so the narration cannot be pulled towards the written sequence."""
    L = [f"TASK: {g.name}", (g.description or "").strip(), ""]
    if g.objects:
        L.append("OBJECTS: " + "; ".join(o.name + (f" (also {', '.join(o.aliases)})" if o.aliases else "")
                                        for o in g.objects))
        L.append("")
    acts = sorted({(n.description or n.name).strip().rstrip(".") for n in g.nodes if n.is_step}, key=str.lower)
    L.append("ACTIONS THIS PROCEDURE INVOLVES (alphabetical; NOT the order they should happen in; some may not happen):")
    L += [f"  - {a}" for a in acts]
    return "\n".join(L)


def narrate_prompt(ctx: str, duration: float) -> str:
    return (f"{ctx}\n\nVideo length: {duration:.1f} s.\n\n"
            "Write the complete timeline of what happens in this video, in the order it happens, as specified. "
            "Describe what you see, not what the procedure expects; an action that does not happen must not appear; "
            "an action outside the list must appear; an action done again after it was finished is a new entry.")


def _mmss_to_s(v: float) -> float:
    m = int(v) // 100
    return m * 60 + (v - m * 100)


def normalize_narration_times(narr: dict, duration: float) -> dict:
    """Timestamps must be seconds. Models sometimes write minutes and seconds as one number (4:35 -> 435).
    Detect that per narration: the timeline then runs past the video's end and/or every value has a
    'seconds' part below 60. If reinterpreting as MM:SS keeps every value inside the video, apply it.
    Otherwise a timeline running past the end is a uniformly stretched clock: rescale it to the video
    length. Records what was done in narr['time_fix']. Always clamps to [0, duration] afterwards."""
    acts = narr.get("actions", []) or []
    vals = [float(a.get(k, 0) or 0) for a in acts for k in ("start_s", "end_s")]
    fix = "none"
    if vals:
        over = max(vals) > duration * 1.03 + 2.0
        big = [v for v in vals if v >= 100]  # values below 100 read the same either way
        looks_mmss = bool(big) and all((v % 100) < 60 for v in big)
        converted = False
        if over and looks_mmss:
            conv = [_mmss_to_s(v) if v >= 100 else v for v in vals]
            if max(conv) <= duration * 1.05 + 2.0:
                for a in acts:
                    a["start_s"] = _mmss_to_s(float(a["start_s"])) if float(a["start_s"]) >= 100 else float(a["start_s"])
                    a["end_s"] = _mmss_to_s(float(a["end_s"])) if float(a["end_s"]) >= 100 else float(a["end_s"])
                fix, converted = "mmss->seconds", True
        if over and not converted:
            scale = duration / max(vals)
            for a in acts:
                a["start_s"], a["end_s"] = float(a["start_s"]) * scale, float(a["end_s"]) * scale
            fix = f"scaled x{scale:.3f}"
    for a in acts:
        a["start_s"] = max(0.0, min(duration, float(a["start_s"])))
        a["end_s"] = max(a["start_s"], min(duration, float(a["end_s"])))
    narr["time_fix"] = fix
    return narr


# ------------------------------------------------------------------------------------------
# match
# ------------------------------------------------------------------------------------------
MATCH_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "matches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "step_ids": {"type": "array", "items": {"type": "string"}},
                    "candidates": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                },
                "required": ["index", "step_ids", "candidates", "reason"],
            },
        },
    },
    "required": ["matches"],
}


def match_prompt(ctx: str, narr_text: str) -> str:
    return (f"=== PROCEDURE ===\n{ctx}\n\n=== NARRATION ===\n{narr_text}\n\n"
            "Return one match per narration entry, by index.")


def narration_text(narr: dict, with_matches: bool = True) -> str:
    head = "TIMELINE (index. start-end s | hand | action | state change" + (" | matched step" if with_matches else "") + "):"
    L = [f"SCENE AT START: {narr.get('scene_start', '')}", "", head]
    for i, a in enumerate(narr.get("actions", []) or []):
        loc = ""
        if a.get("from_location") or a.get("to_location"):
            loc = f" from {a.get('from_location') or '?'} to {a.get('to_location') or '?'}"
        q = f" | {a['quantity_or_setting']}" if a.get("quantity_or_setting") else ""
        cnt = f" x{a['count']}" if (a.get("count") or 1) > 1 else ""
        sc = " | SCENE CHANGE" if a.get("scene_change") else ""
        m = ""
        if with_matches:
            m = f" | {' + '.join(a.get('matched_step_ids') or ([a['matched_step_id']] if a.get('matched_step_id') else [])) or '-'}"
            alt = [c for c in (a.get("candidates") or []) if c != a.get("matched_step_id")]
            if a.get("continues_entry") is not None:
                m += f" (continues #{a['continues_entry']}, same performance)"
            elif alt:
                m += f" (look-alike of {', '.join(alt)})"
        L.append(f"  #{i}. {float(a.get('start_s', 0)):.1f}-{float(a.get('end_s', 0)):.1f} s | {a.get('hand', '?')} | "
                 f"{a.get('verb', '?')} {a.get('object', '?')}{loc}{cnt} | {a.get('state_change', '')}{q}{sc}{m} "
                 f"(conf {float(a.get('confidence', 0)):.2f})")
    L += ["", f"SCENE AT END: {narr.get('scene_end', '')}", f"OBSERVER NOTES: {narr.get('notes', '')}"]
    return "\n".join(L)


def _required(g: TaskGraph, sid: str) -> List[str]:
    return [p for p in ops.required_predecessors(g, sid) if p in g.node_map and g.node_map[p].is_step]


# function words and time units: they never tell two step texts apart
_STOP = {"the", "a", "an", "of", "to", "on", "in", "into", "onto", "with", "for", "and", "or", "at", "by", "from",
         "it", "its", "this", "that", "more", "about", "until", "just", "again", "then", "second", "seconds",
         "minute", "minutes", "hour", "hours"}


def _tokens(text: str) -> set:
    return {w for w in re.sub(r"[^a-z ]", " ", text.lower()).split() if len(w) > 2 and w not in _STOP}


def _content_names(a: dict, g: TaskGraph, sid: str, pool: Sequence[str], pick: str) -> bool:
    """True when the entry itself names something only the matcher's step has: then content decides and
    the position rule must not override it."""
    nm = g.node_map
    toks = {s: _tokens(nm[s].description or nm[s].name) for s in pool}
    own = toks[sid] - set().union(*(toks[s] for s in pool if s != sid))
    other = toks[pick] - set().union(*(toks[s] for s in pool if s != pick))
    seen = _tokens(" ".join(str(a.get(k) or "") for k in ("verb", "object", "state_change", "quantity_or_setting")))
    return bool(own & seen) and not (other & seen)


def resolve_lookalikes(g: TaskGraph, actions: Sequence[dict], order: Sequence[str],
                       convention: str = IDENTITY_CONVENTION) -> int:
    """Apply the identity convention to entries whose candidates are several steps. Walks the entries
    in time order keeping the set of performed steps; among the candidates, picks the latest step (in
    procedure order) whose required steps are all performed and that still has repeats left. Sets
    matched_step_id in place and records the matcher's own choice as matched_by_content.
    An entry of the same look-alike group that directly follows the previous one, with no other step
    matched in between, continues that step instance: it gets the same id and `continues_entry`, and is
    not counted as a new performance. Returns the number of entries re-assigned."""
    if convention != "position":
        return 0
    pos = {s: i for i, s in enumerate(order)}
    nm = g.node_map
    done: Dict[str, int] = {}
    changed = 0
    last = None  # (entry index, step id, pool) of the previous look-alike entry, while nothing else happened
    for i, a in enumerate(actions):
        sids = list(a.get("matched_step_ids") or ([a["matched_step_id"]] if a.get("matched_step_id") else []))
        sid = sids[0] if len(sids) == 1 else None
        cands = [c for c in (a.get("candidates") or []) if c in pos]
        if sid in pos and len(set(cands) | {sid}) > 1 and last and set(last[2]) & (set(cands) | {sid}) \
                and not (sid != last[1] and _content_names(a, g, sid, sorted(set(last[2]) | {sid}), last[1])):
            if last[1] != sid:
                a["matched_by_content"] = sid
                changed += 1
            a["matched_step_id"], a["matched_step_ids"], a["continues_entry"] = last[1], [last[1]], last[0]
            continue
        if sids:
            last = None
        if sid in pos and len(set(cands) | {sid}) > 1:
            pool = sorted(set(cands) | {sid}, key=lambda s: pos[s])
            ok = [s for s in pool if all(done.get(r, 0) > 0 for r in _required(g, s))
                  and done.get(s, 0) < nm[s].permitted_repeats]
            pick = ok[-1] if ok else sid
            if pick != sid and not _content_names(a, g, sid, pool, pick):
                a["matched_by_content"] = sid
                a["matched_step_id"] = pick
                a["matched_step_ids"] = [pick]
                sids = [pick]
                changed += 1
            last = (i, sids[0], pool)
        for x in sids:
            if x in pos:
                done[x] = done.get(x, 0) + 1
    return changed


def apply_matches(narr: dict, data: dict, step_ids: Sequence[str]) -> None:
    ids = set(step_ids)
    by = {}
    for m in (data or {}).get("matches", []) or []:
        try:
            by[int(m.get("index"))] = m
        except (TypeError, ValueError):
            continue
    for i, a in enumerate(narr.get("actions", []) or []):
        m = by.get(i, {})
        raw = m.get("step_ids")
        if raw is None:
            raw = [m.get("step_id")]
        sids = [x for x in (str(r or "").strip("[] ") for r in raw) if x in ids]
        a["matched_step_ids"] = list(dict.fromkeys(sids))
        a["matched_step_id"] = a["matched_step_ids"][0] if a["matched_step_ids"] else None
        a["candidates"] = [c for c in (str(x).strip("[] ") for x in (m.get("candidates") or [])) if c in ids]
        a["match_reason"] = str(m.get("reason", ""))[:120]
        if a.get("scene_change"):
            a["matched_step_id"], a["matched_step_ids"], a["candidates"] = None, [], []


def match_narration(g: TaskGraph, narr: dict, text_client, text_model: Optional[str] = None) -> dict:
    """Assign steps to the narration entries (in place): one text call, then the look-alike convention."""
    ctx, order = graph_context(g)
    for a in narr.get("actions", []) or []:
        for k in ("matched_step_id", "matched_step_ids", "candidates", "match_reason", "matched_by_content",
                  "continues_entry"):
            a.pop(k, None)
    with pricing.timed_stage("match"):
        mdata = text_client.complete_json(prompts.get("narration.match.system"),
                                          match_prompt(ctx, narration_text(narr, with_matches=False)),
                                          schema=MATCH_SCHEMA, schema_name="matches", model=text_model, max_tokens=12000,
                                          reasoning_effort=MATCH_REASONING_EFFORT)
    apply_matches(narr, mdata if isinstance(mdata, dict) else {}, order)
    narr["identity_convention"] = IDENTITY_CONVENTION
    narr["n_reassigned_lookalikes"] = resolve_lookalikes(g, narr.get("actions", []) or [], order)
    return narr


# ------------------------------------------------------------------------------------------
# the performed step sequence
# ------------------------------------------------------------------------------------------
Step = Tuple[int, str, float, float, float]  # (entry index, step id, start_s, end_s, confidence)


def _entry_steps(a: dict) -> List[str]:
    sids = a.get("matched_step_ids")
    if sids is None:
        sids = [a.get("matched_step_id")] if a.get("matched_step_id") else []
    return [str(s or "").strip("[] ") for s in sids]


def performed_sequence(g: TaskGraph, narration: dict) -> List[Step]:
    """Every (entry, step) pair in time order: an entry performing several steps gives several pairs."""
    ids = {n.id for n in g.nodes if n.is_step}
    out: List[Step] = []
    for i, a in enumerate(narration.get("actions", []) or []):
        for s in _entry_steps(a):
            if s in ids:
                out.append((i, s, float(a.get("start_s", 0) or 0), float(a.get("end_s", 0) or 0),
                            float(a.get("confidence", 0.5) or 0.5)))
    return out


def performed_spans(g: TaskGraph, narration: dict) -> Dict[str, List[tuple]]:
    """step id -> [(entry index, start_s, end_s)] of the entries matched to it."""
    out: Dict[str, List[tuple]] = {}
    for i, s, a, b, _ in performed_sequence(g, narration):
        out.setdefault(s, []).append((i, a, b))
    return out


def video_duration(video_path: str) -> float:
    from procqc.signals.frames import VideoReader
    with VideoReader(video_path) as v:
        return float(v.duration)


def narrated_sequence(g: TaskGraph, video_path: str, gclient, text_client) -> tuple:
    """Narration (cached: one video call per recording, shared by every check) + match stage.
    Returns (duration, narration with matches, performed step sequence)."""
    duration = video_duration(video_path)
    with pricing.timed_stage("narrate"):
        narr = gclient.ask(video_path, prompts.get("narration.narrate.system"),
                           narrate_prompt(narrator_context(g), duration), NARRATE_SCHEMA, stage="narrate")
    narr = normalize_narration_times(json.loads(json.dumps(narr)), duration)
    match_narration(g, narr, text_client)
    return duration, narr, performed_sequence(g, narr)
