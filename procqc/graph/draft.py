"""Draft a task graph (version 1 schema) from SOP / work-instruction text with an LLM (via Fuelix),
then lint and repair in a bounded loop.

The system prompt is `prompts.GRAPH_DRAFT_SYSTEM`; the user message (SOP, hints, schema) and the
repair message are built here. Every output is validated by the schema and the structural linter before it is accepted;
lint errors are fed back for at most ``max_rounds`` repair attempts.
"""
from __future__ import annotations

import datetime as _dt
import json
from typing import List, Optional, Sequence

from pydantic import ValidationError

from procqc import pricing, prompts
from procqc.graph.linter import LintIssue, format_issues, lint
from procqc.graph.schema import Provenance, TaskGraph
from procqc.llm_client import LLMClient

CHECKER_KEYS = [
    "gripper_width",   # grasp / release from gripper opening
    "ft_contact",      # force/torque contact or release event
    "proprio_pose",    # end-effector / joint pose region
    "detector",        # open-vocabulary object detector (identity / presence / location)
    "vlm_effect",      # VLM judgement on effect frames (state predicates)
    "kinematic_idle",  # stillness / settle
    "manual",          # human-only
]

def _normalize(data: dict) -> dict:
    """Repair common, meaning-preserving model slips before schema validation.

    * END node carrying preconditions -> merged into `goal` (they mean the same thing).
    * START node carrying effects -> merged into `initial_state`.
    * Substitutes / target objects that are not declared -> declared as stub objects, so the
      graph is usable; the linter still reports W013/W017 for a human to fill in names/aliases.
    """
    if not isinstance(data, dict):
        return data
    nodes = data.get("nodes") or []
    goal = list(data.get("goal") or [])
    init = list(data.get("initial_state") or [])
    for n in nodes:
        if not isinstance(n, dict):
            continue
        if n.get("kind") == "end":
            goal.extend(n.get("preconditions") or [])
            n["preconditions"], n["effects"] = [], []
        elif n.get("kind") == "start":
            init.extend(n.get("effects") or [])
            n["preconditions"], n["effects"] = [], []
    data["goal"], data["initial_state"] = goal, init

    declared = {o.get("id") for o in (data.get("objects") or []) if isinstance(o, dict)}
    referenced = set()
    for o in data.get("objects") or []:
        referenced.update(o.get("substitutes") or [])
    for n in nodes:
        if not isinstance(n, dict):
            continue
        referenced.update(n.get("target_objects") or [])
        referenced.update(n.get("tools") or [])
        for subs in (n.get("allowed_substitutes") or {}).values():
            referenced.update(subs or [])
        for p in (n.get("preconditions") or []) + (n.get("effects") or []):
            referenced.update(p.get("args") or [])
    for p in goal + init:
        if isinstance(p, dict):
            referenced.update(p.get("args") or [])
    missing = sorted(r for r in referenced if isinstance(r, str) and r and r not in declared)
    if missing:
        data.setdefault("objects", [])
        data["objects"].extend({"id": m, "name": m.replace("_", " "), "category": "",
                                "aliases": [], "substitutes": []} for m in missing)
    return data

USER = """SOP / work instructions:
\"\"\"
{sop}
\"\"\"

{extras}
JSON schema of the expected output:
{schema}
"""

REPAIR = """The task graph you produced has the following lint issues. Fix ALL errors and as many
warnings as you can WITHOUT changing the meaning of the procedure.

Return the COMPLETE corrected JSON object (not a diff). Preserve every node, edge, object,
predicate, effect, checker, pitfall and description from the previous graph unless an issue
explicitly requires changing it. A repaired graph that has fewer effects, objects or
checkers than the previous one will be rejected.

Issues:
{issues}

Previous graph:
{graph}
"""


# Fields the LLM must always emit. Pydantic marks them optional (they have defaults), but under
# schema-constrained decoding a model may legally stop once the *required* fields are present and
# silently drop everything else (observed with gemini-3.8-flash via Fuelix: no effects, no
# objects, no checkers). Making them required in the LLM-facing schema forces complete output;
# TaskGraph.model_validate still accepts the result because defaults remain defaults.
_REQUIRED_BY_MODEL = {
    "TaskGraph": ["task_id", "name", "domain", "description", "objects", "initial_state", "goal",
                  "nodes", "edges"],
    "Node": ["id", "name", "kind", "description", "preconditions", "effects", "optional",
             "mandatory_terminal", "permitted_repeats", "target_objects", "tools",
             "effect_description", "pitfalls"],
    "Predicate": ["name", "args", "value", "checker"],
    "ObjectSpec": ["id", "name", "category", "aliases", "substitutes"],
    "Edge": ["source", "target", "relation", "condition"],
}
_DROP_FROM_MODEL_SCHEMA = {"TaskGraph": ["provenance", "metadata", "version"]}


def _llm_schema() -> dict:
    """TaskGraph JSON schema adapted for the model: key fields required, bookkeeping removed."""
    schema = TaskGraph.model_json_schema()
    defs = schema.get("$defs", {})
    for name, req in _REQUIRED_BY_MODEL.items():
        target = schema if name == "TaskGraph" else defs.get(name)
        if not target:
            continue
        props = target.get("properties", {})
        for drop in _DROP_FROM_MODEL_SCHEMA.get(name, []):
            props.pop(drop, None)
        target["required"] = [r for r in req if r in props]
    return schema


def _schema_json() -> str:
    return json.dumps(_llm_schema(), separators=(",", ":"))


def _richness(data: dict) -> tuple:
    """Content measure used to refuse repairs that strip the graph (validation gating)."""
    nodes = data.get("nodes", []) or []
    n_pred = sum(len(n.get("preconditions") or []) + len(n.get("effects") or []) for n in nodes)
    return (len(nodes), n_pred, len(data.get("objects") or []), len(data.get("edges") or []))


def draft_graph(
    sop_text: str,
    task_id: str,
    domain: str = "",
    object_hints: Optional[Sequence[str]] = None,
    demo_sequences: Optional[Sequence[Sequence[str]]] = None,
    client: Optional[LLMClient] = None,
    model: Optional[str] = None,
    max_rounds: int = 2,
    known_checkers: Optional[set] = None,
    verbose: bool = False,
) -> TaskGraph:
    """Draft, lint, and repair. Raises RuntimeError if errors remain after max_rounds."""
    client = client or LLMClient()
    model = model or client.model
    extras: List[str] = [f"task_id: {task_id}", f"domain: {domain or 'unspecified'}"]
    if object_hints:
        extras.append("Known objects / part numbers (use these ids where they fit): "
                      + ", ".join(object_hints))
    if demo_sequences:
        sample = [list(s) for s in list(demo_sequences)[:5]]
        extras.append("Observed clean step sequences from annotators. USE THESE EXACT STEP IDS as node "
                      "ids for the corresponding steps (add new ids only for steps the SOP requires "
                      "that never appear here). Use the order variation across sequences to decide "
                      "parallelism, and steps missing from some sequences to decide optional=true:\n"
                      + json.dumps(sample))
    user = USER.format(sop=sop_text.strip(), extras="\n".join(extras) + "\n", schema=_schema_json())
    schema = _llm_schema()
    system = prompts.get("graph.draft.system")
    _stage = pricing.use_stage("graph_draft")
    _stage.__enter__()
    data = client.complete_json(system, user, schema=schema, schema_name="task_graph", model=model)

    # Validation-gated repair loop: keep the best candidate seen (fewest errors, then fewest
    # warnings, then richest content) and refuse repairs that strip content.
    best: Optional[tuple] = None  # (n_errors, n_warnings, -richness, graph, issues)
    graph: Optional[TaskGraph] = None
    issues: List[LintIssue] = []
    checkers = known_checkers or set(CHECKER_KEYS)
    for rnd in range(max_rounds + 1):
        try:
            data = _normalize(data)
            cand = TaskGraph.model_validate(data)
            cand_issues = lint(cand, known_checkers=checkers)
            n_err = sum(1 for i in cand_issues if i.severity.value == "error")
            rich = _richness(data)
            if verbose:
                print(f"[draft] round {rnd}: {n_err} errors, {len(cand_issues) - n_err} warnings, "
                      f"nodes/preds/objects/edges={rich}")
            key = (n_err, len(cand_issues) - n_err, tuple(-x for x in rich))
            stripped = best is not None and rich[1] < best[2][1] * 0.8  # lost >20% of predicates
            if best is None or (key < best[0] and not stripped):
                best = (key, cand, rich, cand_issues)
            elif verbose:
                print("[draft]   candidate rejected (regression or stripped content)")
            problems = format_issues(cand_issues) if cand_issues else ""
            if n_err == 0:
                break
        except ValidationError as exc:
            problems = "SCHEMA VALIDATION ERRORS:\n" + str(exc)[:4000]
            if verbose:
                print(f"[draft] round {rnd}: schema validation failed")
        if rnd == max_rounds:
            if best is not None and best[0][0] == 0:
                break
            raise RuntimeError(f"graph still invalid after {max_rounds} repair rounds:\n{problems}")
        data = client.complete_json(
            system, REPAIR.format(issues=problems, graph=json.dumps(data)[:60000]),
            schema=schema, schema_name="task_graph", model=model,
        )

    _stage.__exit__(None, None, None)
    assert best is not None
    _, graph, _, issues = best
    if best[0][0] > 0:
        raise RuntimeError("no error-free graph produced:\n" + format_issues(issues))
    graph.provenance = Provenance(
        source="llm_draft", model=model,
        created_at=_dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        notes=[f"{len(issues)} lint warnings at acceptance",
               f"usage prompt={client.total_usage.prompt_tokens} completion={client.total_usage.completion_tokens} "
               f"usd={pricing.GLOBAL_METER.by_stage.get('graph_draft', {}).get('usd', 0.0):.4f}"],
    )
    if domain and not graph.domain:
        graph.domain = domain
    graph.task_id = task_id
    return graph
