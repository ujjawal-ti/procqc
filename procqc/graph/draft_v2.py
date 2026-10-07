"""Draft a version 2 task graph (`procqc/graph/schema_v2.py`) from an SOP, via Fuelix. Version 1's drafter
(`procqc/graph/draft.py`) stays unchanged.

Two stages, then version 1's validation-gated lint-repair loop:
  1. extract   every SOP sentence is sorted into fixed fields (scenario, objects at category level with
               their kinds, starting state, steps, repeat, acceptance criteria, constraints, not modelled),
               each with the SOP text it comes from, verbatim. SOP layouts differ between tasks; this stage
               absorbs that.
  2. graph     the graph is built from the extraction (version 1 structure plus the version 2 fields).
  normalize    deterministic: an element whose quote is not in the SOP is marked inferred; steps inside a
               repeat block get permitted_repeats = UNBOUNDED; constraints are filed under "violation".
  lint         version 1's linter plus `procqc/graph/linter_v2.py` (repeat end conditions, every SOP
               sentence accounted for).
System prompts: `prompts.SOP_EXTRACT_SYSTEM` and `prompts.GRAPH_V2_SYSTEM` (principles only).

Usage (from the repository root):
  python3 -m procqc.graph.cli draft-v2 SOP.md OUT.yaml --task-id X [--domain D] [--model M]
      writes OUT.yaml and OUT.extract.json
"""
from __future__ import annotations

import datetime as _dt
import json
from typing import Optional

from pydantic import ValidationError

from procqc import pricing, prompts
from procqc.graph import draft as D1
from procqc.graph.linter import format_issues
from procqc.graph.linter_v2 import lint_v2, quote_in_sop, sources
from procqc.graph.schema import Provenance
from procqc.graph.schema_v2 import UNBOUNDED, VIOLATION, TaskGraphV2
from procqc.llm_client import LLMClient

# ------------------------------------------------------------------------------------------
# 1. extract
# ------------------------------------------------------------------------------------------
_Q = {"quote": {"type": "string"}}
EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "scenario": {"type": "object", "properties": {**{k: {"type": "string"} for k in (
            "activity_type", "site_id", "location", "scene_type", "country")},
            "other": {"type": "object", "additionalProperties": {"type": "string"}}, **_Q},
            "required": ["activity_type", "site_id", "location", "scene_type", "country", "quote"]},
        "objects": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "role": {"type": "string"}, "kinds": {"type": "array", "items": {"type": "string"}}, **_Q},
            "required": ["name", "role", "kinds", "quote"]}},
        "starting_state": {"type": "array", "items": {"type": "object", "properties": {"fact": {"type": "string"}, **_Q},
                                                      "required": ["fact", "quote"]}},
        "steps": {"type": "array", "items": {"type": "object", "properties": {
            "number": {"type": "integer"}, "text": {"type": "string"}, **_Q}, "required": ["number", "text", "quote"]}},
        "repeat": {"type": "object", "properties": {
            "present": {"type": "boolean"}, "step_numbers": {"type": "array", "items": {"type": "integer"}},
            "unit": {"type": "string"}, "end_condition": {"type": "string"}, "count": {"type": "string"}, **_Q},
            "required": ["present", "step_numbers", "unit", "end_condition", "count", "quote"]},
        "acceptance": {"type": "array", "items": {"type": "object", "properties": {
            "step_number": {"type": "integer"}, "criterion": {"type": "string"}, **_Q},
            "required": ["step_number", "criterion", "quote"]}},
        "constraints": {"type": "array", "items": {"type": "object", "properties": {
            "rule": {"type": "string"}, "step_numbers": {"type": "array", "items": {"type": "integer"}},
            "violation_looks_like": {"type": "string"}, **_Q},
            "required": ["rule", "step_numbers", "violation_looks_like", "quote"]}},
        "not_modelled": {"type": "array", "items": {"type": "object", "properties": {"reason": {"type": "string"}, **_Q},
                                                    "required": ["reason", "quote"]}},
    },
    "required": ["scenario", "objects", "starting_state", "steps", "repeat", "acceptance", "constraints", "not_modelled"],
}


def extract(sop: str, client: LLMClient, model: Optional[str] = None, use_cache: bool = True) -> dict:
    with pricing.timed_stage("graph_draft_v2_extract"):
        d = client.complete_json(prompts.get("graph.v2.extract.system"), f'SOP:\n"""\n{sop.strip()}\n"""\nReturn the JSON.', schema=EXTRACT_SCHEMA,
                                 schema_name="sop_fields", model=model, max_tokens=8000, use_cache=use_cache)
    return d if isinstance(d, dict) else {}


# ------------------------------------------------------------------------------------------
# 2. graph
# ------------------------------------------------------------------------------------------
_REQUIRED_BY_MODEL_V2 = {
    "TaskGraphV2": ["task_id", "name", "domain", "description", "objects", "initial_state", "goal", "nodes", "edges",
                    "scenario", "starting_state", "repeat_blocks", "acceptance", "constraints", "not_modelled"],
    "NodeV2": D1._REQUIRED_BY_MODEL["Node"] + ["source"],
    "ObjectSpecV2": D1._REQUIRED_BY_MODEL["ObjectSpec"] + ["kinds", "source"],
    "Predicate": D1._REQUIRED_BY_MODEL["Predicate"],
    "Edge": D1._REQUIRED_BY_MODEL["Edge"],
    "Source": ["quote", "inferred"],
    "StateFact": ["description", "objects", "predicates", "source"],
    "RepeatBlock": ["id", "steps", "unit", "objects", "until", "until_description", "count_hint", "source"],
    "Acceptance": ["id", "step", "objects", "criterion", "predicate", "per_object", "source"],
    "Constraint": ["id", "rule", "applies_to", "violation_looks_like", "taxonomy", "source"],
    "Scenario": ["activity_type", "site_id", "location", "scene_type", "country", "source"],
    "NotModelled": ["quote", "reason"],
}
_DROP = {"TaskGraphV2": ["provenance", "metadata", "version", "schema_version"]}


def llm_schema() -> dict:
    schema = TaskGraphV2.model_json_schema()
    defs = schema.get("$defs", {})
    for name, req in _REQUIRED_BY_MODEL_V2.items():
        target = schema if name == "TaskGraphV2" else defs.get(name)
        if not target:
            continue
        props = target.get("properties", {})
        for drop in _DROP.get(name, []):
            props.pop(drop, None)
        target["required"] = [r for r in req if r in props]
    return schema


def normalize(data: dict, sop: str) -> dict:
    """Version 1's repairs, then version 2's deterministic rules."""
    data = D1._normalize(data)
    if not isinstance(data, dict):
        return data

    def fix(src):
        if not isinstance(src, dict):
            return {"quote": "", "inferred": True}
        src["inferred"] = not quote_in_sop(src.get("quote", ""), sop)
        return src

    for key in ("objects", "nodes", "starting_state", "repeat_blocks", "acceptance", "constraints"):
        for x in data.get(key) or []:
            if isinstance(x, dict) and key == "nodes" and x.get("kind") in ("start", "end"):
                x["source"] = {"quote": "", "inferred": False}  # start and end are structural, not SOP text
            elif isinstance(x, dict):
                x["source"] = fix(x.get("source"))
    if isinstance(data.get("scenario"), dict):
        data["scenario"]["source"] = fix(data["scenario"].get("source"))
    in_block = {s for b in data.get("repeat_blocks") or [] if isinstance(b, dict) for s in b.get("steps") or []}
    for n in data.get("nodes") or []:
        if isinstance(n, dict) and n.get("id") in in_block:
            n["permitted_repeats"] = UNBOUNDED
    for c in data.get("constraints") or []:
        if isinstance(c, dict):
            c["taxonomy"] = VIOLATION
            c["applies_to"] = c.get("applies_to") or ["*"]
    return data


def draft_graph_v2(sop: str, task_id: str, domain: str = "", client: Optional[LLMClient] = None,
                   model: Optional[str] = None, max_rounds: int = 2, verbose: bool = False,
                   use_cache: bool = True) -> tuple:
    """Returns (graph, extraction, lint issues at acceptance). Raises RuntimeError if errors remain."""
    client = client or LLMClient()
    model = model or client.model
    fields = extract(sop, client, model, use_cache)
    schema = llm_schema()
    user = (f'SOP:\n"""\n{sop.strip()}\n"""\n\nFIELD EXTRACTION:\n{json.dumps(fields, indent=1)}\n\n'
            f"task_id: {task_id}\ndomain: {domain or 'unspecified'}\n\nJSON schema of the expected output:\n"
            f"{json.dumps(schema, separators=(',', ':'))}\n")
    checkers = set(D1.CHECKER_KEYS)
    system = prompts.get("graph.v2.build.system")
    with pricing.timed_stage("graph_draft_v2"):
        data = client.complete_json(system, user, schema=schema, schema_name="task_graph_v2", model=model,
                                    max_tokens=16000, use_cache=use_cache)
        best = None
        problems = ""
        for rnd in range(max_rounds + 1):
            try:
                data = normalize(data, sop)
                cand = TaskGraphV2.model_validate(data)
                issues = lint_v2(cand, sop, known_checkers=checkers)
                n_err = sum(1 for i in issues if i.severity.value == "error")
                rich = D1._richness(data) + (len(cand.acceptance), len(cand.constraints), len(cand.repeat_blocks))
                key = (n_err, len(issues) - n_err, tuple(-x for x in rich))
                if verbose:
                    print(f"[draft_v2] round {rnd}: {n_err} errors, {len(issues) - n_err} warnings, content={rich}")
                stripped = best is not None and rich[1] < best[2][1] * 0.8
                if best is None or (key < best[0] and not stripped):
                    best = (key, cand, rich, issues)
                problems = format_issues(issues) if issues else ""
                if n_err == 0:
                    break
            except ValidationError as exc:
                problems = "SCHEMA VALIDATION ERRORS:\n" + str(exc)[:4000]
                if verbose:
                    print(f"[draft_v2] round {rnd}: schema validation failed")
            if rnd == max_rounds:
                break
            data = client.complete_json(system, D1.REPAIR.format(issues=problems, graph=json.dumps(data)[:60000]),
                                        schema=schema, schema_name="task_graph_v2", model=model, max_tokens=16000,
                                        use_cache=use_cache)
    if best is None or best[0][0] > 0:
        raise RuntimeError("no error-free version 2 graph produced:\n" + problems)
    _, graph, _, issues = best
    usd = sum(pricing.GLOBAL_METER.by_stage.get(s, {}).get("usd", 0.0) for s in ("graph_draft_v2_extract", "graph_draft_v2"))
    n_inf = sum(1 for _, s in sources(graph) if s.inferred)
    graph.provenance = Provenance(
        source="llm_draft_v2", model=model,
        created_at=_dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        notes=[f"{len(issues)} lint warnings at acceptance", f"{n_inf} inferred elements", f"usd={usd:.4f}"])
    graph.task_id = task_id
    if domain and not graph.domain:
        graph.domain = domain
    return graph, fields, issues
