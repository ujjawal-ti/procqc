"""Task graph schema, version 2: what a written SOP states, with the SOP sentence behind every element.
Version 1 (`procqc/graph/schema.py`) stays unchanged.

Version 1 holds steps, edges, predicates and per-step QC attributes. An SOP for a household or
demonstration task also states things version 1 cannot hold, so the drafter dropped them or kept them as
free text no check reads. Version 2 adds, all optional:

  scenario         activity type, site, location, scene type, country (the SOP's "Applicable Scenario").
  source           on every element: the SOP sentence it came from, or inferred=true when the drafter
                   added it (an inferred element may only send a recording to review, never confirm a flag).
  objects          named at category level; `kinds` lists the varieties the SOP names, and any kind of
                   the object counts as the object (a variety is not a substitution).
  starting_state   where the task objects are at the start, and what the destination already holds.
                   Termination, omission and off-graph addition depend on it.
  repeat_blocks    consecutive steps done once per object (or per group of objects), with no fixed count:
                   the block ends when its end condition holds. Steps inside a block carry
                   permitted_repeats = UNBOUNDED, so version 1 checks do not flag the cycle as a repeat.
  acceptance       the criteria the SOP sets for the result of a step, per object (placement, orientation,
                   arrangement, state).
  constraints      rules the SOP forbids or requires across steps ("Constraints / Avoid"). Breaking one is
                   reported under the "violation" taxonomy (to be split into finer kinds later).
  not_modelled     SOP sentences deliberately kept out of the graph (collection or reset instructions,
                   durations handled by another check), with the reason, so every SOP sentence is accounted for.

A version 2 graph file is still a valid version 1 graph: `procqc.graph.io.load_graph` ignores the added
fields, so every existing check runs on it unchanged.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from procqc.graph.schema import Node, ObjectSpec, Predicate, TaskGraph

UNBOUNDED = 999  # permitted_repeats for steps in a repeat block: the block's end condition decides
VIOLATION = "violation"


class Source(BaseModel):
    quote: str = Field(default="", description="The SOP sentence (or the part of it) this element comes from, verbatim")
    inferred: bool = Field(default=False, description="True when the SOP does not state it (added by the drafter)")


class Scenario(BaseModel):
    activity_type: str = ""
    site_id: str = ""
    location: str = ""
    scene_type: str = ""
    country: str = ""
    other: Dict[str, str] = Field(default_factory=dict, description="Other scenario fields, verbatim")
    source: Source = Field(default_factory=Source)


class ObjectSpecV2(ObjectSpec):
    kinds: List[str] = Field(default_factory=list,
                             description="Varieties of this object the SOP names; every kind counts as this object")
    source: Source = Field(default_factory=Source)


class NodeV2(Node):
    source: Source = Field(default_factory=Source)


class StateFact(BaseModel):
    description: str = Field(..., description="One fact about the scene at the start, in words")
    objects: List[str] = Field(default_factory=list, description="Object ids it is about")
    predicates: List[Predicate] = Field(default_factory=list)
    source: Source = Field(default_factory=Source)


class RepeatBlock(BaseModel):
    id: str
    steps: List[str] = Field(..., description="Consecutive step ids performed once per unit, in order")
    unit: str = Field(..., description="What one round handles, including any choice the SOP allows")
    objects: List[str] = Field(default_factory=list, description="Object ids the rounds go through")
    until: List[Predicate] = Field(default_factory=list, description="Cumulative end condition (scope cumulative)")
    until_description: str = Field(..., description="The end condition in words")
    count_hint: str = Field(default="", description="How many units the SOP expects, verbatim; a hint, not a limit")
    source: Source = Field(default_factory=Source)


class Acceptance(BaseModel):
    id: str
    step: str = Field(..., description="Step id whose result the criterion is about")
    objects: List[str] = Field(default_factory=list)
    criterion: str = Field(..., description="One checkable criterion, in words")
    predicate: Optional[Predicate] = None
    per_object: bool = Field(default=True, description="Checked for each object the step handles")
    source: Source = Field(default_factory=Source)


class Constraint(BaseModel):
    id: str
    rule: str = Field(..., description="The rule as the SOP states it")
    applies_to: List[str] = Field(default_factory=lambda: ["*"], description="Step ids, or ['*'] for the whole task")
    violation_looks_like: str = Field(..., description="What breaking the rule looks like on video, observable")
    taxonomy: str = VIOLATION
    source: Source = Field(default_factory=Source)


class NotModelled(BaseModel):
    quote: str
    reason: str


class TaskGraphV2(TaskGraph):
    schema_version: str = "2"
    objects: List[ObjectSpecV2] = Field(default_factory=list)
    nodes: List[NodeV2]
    scenario: Optional[Scenario] = None
    starting_state: List[StateFact] = Field(default_factory=list)
    repeat_blocks: List[RepeatBlock] = Field(default_factory=list)
    acceptance: List[Acceptance] = Field(default_factory=list)
    constraints: List[Constraint] = Field(default_factory=list)
    not_modelled: List[NotModelled] = Field(default_factory=list)

    @model_validator(mode="after")
    def _v2_shape(self) -> "TaskGraphV2":
        steps = [n.id for n in self.nodes if n.is_step]
        pos = {s: i for i, s in enumerate(steps)}
        for b in self.repeat_blocks:
            bad = [s for s in b.steps if s not in pos]
            if bad:
                raise ValueError(f"repeat block {b.id}: unknown steps {bad}")
            idx = [pos[s] for s in b.steps]
            if idx != list(range(idx[0], idx[0] + len(idx))):
                raise ValueError(f"repeat block {b.id}: steps must be consecutive and in order, got {b.steps}")
        for a in self.acceptance:
            if a.step not in pos:
                raise ValueError(f"acceptance {a.id}: unknown step {a.step!r}")
        for c in self.constraints:
            bad = [s for s in c.applies_to if s != "*" and s not in pos]
            if bad:
                raise ValueError(f"constraint {c.id}: unknown steps {bad}")
        return self

    def block_of(self, step_id: str) -> Optional[RepeatBlock]:
        return next((b for b in self.repeat_blocks if step_id in b.steps), None)


def load_graph_v2(path) -> TaskGraphV2:
    """Load a version 2 graph file (YAML or JSON). `procqc.graph.io.load_graph` reads the same file as version 1."""
    import json
    from pathlib import Path

    import yaml
    p = Path(path)
    text = p.read_text()
    return TaskGraphV2.model_validate(json.loads(text) if p.suffix.lower() == ".json" else yaml.safe_load(text))
