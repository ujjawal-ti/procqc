"""Pydantic schema for the task graph (Python 3.9 compatible).

* Exactly one ``start`` and one ``end`` node.
* Every edge relation except ``CORRECTS`` imposes ordering and must form a DAG.
  ``CORRECTS`` edges are explicit back-edges that legitimise recovery loops, so the
  verifier labels them *correction* instead of *misordering*.
* Preconditions/effects are grounded predicates that name the runtime checker able
  to verify them (gripper width, F/T contact, VLM effect frame, detector...). The
  checker registry lives outside the graph; the graph only references keys.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, field_validator, model_validator

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_\-\.]*$")


class Relation(str, Enum):
    LEADS_TO = "LEADS_TO"  # source must complete before target
    TRIGGERS = "TRIGGERS"  # target applies only if edge.condition holds (still ordered)
    PROVIDES_INPUT_FOR = "PROVIDES_INPUT_FOR"  # object/data dependency (ordered)
    CONVERGES_TO = "CONVERGES_TO"  # parallel branches merge into target (ordered)
    CORRECTS = "CORRECTS"  # back-edge: recovery from source returns to target


PREREQUISITE_RELATIONS = frozenset(
    {Relation.LEADS_TO, Relation.TRIGGERS, Relation.PROVIDES_INPUT_FOR, Relation.CONVERGES_TO}
)


class NodeKind(str, Enum):
    START = "start"
    END = "end"
    STEP = "step"
    CHECK = "check"  # verification / inspection step (protocol-mandated re-check)


class Predicate(BaseModel):
    """Grounded symbolic predicate: Name(object ids) = value."""

    name: str = Field(..., description="CamelCase predicate name")
    args: List[str] = Field(default_factory=list, description="Object ids")
    value: bool = Field(default=True, description="Expected truth value")
    checker: Optional[str] = Field(
        default=None, description="Runtime checker registry key; None = not auto-verifiable"
    )
    scope: Optional[str] = Field(
        default=None,
        description="instance = about the object(s) acted on in this execution; cumulative = about all such "
                    "objects so far; global = about the scene. None = inferred from graph structure "
                    "(effects of repeated steps -> instance, goal -> cumulative, else global).",
    )

    @field_validator("scope")
    @classmethod
    def _scope_ok(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("instance", "cumulative", "global"):
            raise ValueError("scope must be instance | cumulative | global")
        return v

    @field_validator("name")
    @classmethod
    def _name_ok(cls, v: str) -> str:
        if not re.match(r"^[A-Za-z][A-Za-z0-9_]*$", v):
            raise ValueError(f"predicate name must be an identifier, got {v!r}")
        return v

    @property
    def key(self) -> str:
        """Canonical key ignoring truth value, e.g. 'IsOpen(vial)'."""
        return f"{self.name}({','.join(self.args)})"

    def __str__(self) -> str:  # pragma: no cover
        return f"{'' if self.value else '!'}{self.key}"

    @classmethod
    def parse(cls, text: str, checker: Optional[str] = None) -> "Predicate":
        """Parse 'IsOpen(vial)', '!IsOpen(vial)' or 'IsOpen(vial)=False'."""
        s = text.strip()
        value = True
        if s.startswith("!"):
            value, s = False, s[1:]
        if "=" in s:
            s, v = s.rsplit("=", 1)
            value = v.strip().lower() in {"true", "1", "yes"}
        m = re.match(r"^([A-Za-z][A-Za-z0-9_]*)\((.*)\)$", s.strip())
        if not m:
            raise ValueError(f"cannot parse predicate {text!r}")
        args = [a.strip() for a in m.group(2).split(",") if a.strip()]
        return cls(name=m.group(1), args=args, value=value, checker=checker)


class ObjectSpec(BaseModel):
    id: str
    name: str = ""
    category: str = Field(default="", description="tool | part | container | fixture | consumable")
    aliases: List[str] = Field(default_factory=list, description="Detector prompts / synonyms")
    substitutes: List[str] = Field(
        default_factory=list, description="Permissible functional equivalents"
    )
    hazards: List[str] = Field(default_factory=list, description="Regions never to contact")

    @field_validator("id")
    @classmethod
    def _id_ok(cls, v: str) -> str:
        if not _ID_RE.match(v):
            raise ValueError(f"object id must match {_ID_RE.pattern}, got {v!r}")
        return v


class Node(BaseModel):
    id: str
    name: str
    kind: NodeKind = NodeKind.STEP
    description: str = ""
    preconditions: List[Predicate] = Field(default_factory=list)
    effects: List[Predicate] = Field(default_factory=list)

    # QC attributes (boundary rules from the taxonomy guideline)
    optional: bool = Field(default=False, description="May be skipped without an omission flag")
    conditional_on: Optional[Predicate] = Field(
        default=None, description="Required only when this predicate holds"
    )
    mandatory_terminal: bool = Field(
        default=False, description="Must complete before End; missing = early termination"
    )
    permitted_repeats: int = Field(default=1, ge=1, description="Executions before flagging")
    target_objects: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    allowed_substitutes: Dict[str, List[str]] = Field(
        default_factory=dict, description="Per-node: object id -> permissible equivalents"
    )
    expected_duration_s: Optional[Tuple[float, float]] = Field(
        default=None, description="(min, max) plausible duration"
    )
    settle_time_s: float = Field(default=0.0, ge=0.0, description="Static time after completion")
    effect_description: str = Field(
        default="", description="Natural-language post-action state (effect-frame selection)"
    )
    start_rule: str = Field(
        default="", description="When this step is considered to START, when the SOP defines it. "
                                "Overrides the generic first-contact rule."
    )
    end_rule: str = Field(
        default="", description="When this step is considered to END, when the SOP defines it. Overrides the generic "
                                "release rule."
    )
    guidance: str = ""
    pitfalls: List[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _id_ok(cls, v: str) -> str:
        if not _ID_RE.match(v):
            raise ValueError(f"node id must match {_ID_RE.pattern}, got {v!r}")
        return v

    @model_validator(mode="after")
    def _consistency(self) -> "Node":
        if self.optional and self.mandatory_terminal:
            raise ValueError(f"node {self.id}: optional and mandatory_terminal are contradictory")
        if self.kind == NodeKind.END and (self.preconditions or self.effects):
            raise ValueError(f"node {self.id}: END node cannot have preconditions/effects")
        if self.expected_duration_s is not None:
            lo, hi = self.expected_duration_s
            if lo < 0 or hi < lo:
                raise ValueError(f"node {self.id}: expected_duration_s must be 0 <= min <= max")
        return self

    @property
    def is_step(self) -> bool:
        return self.kind in (NodeKind.STEP, NodeKind.CHECK)


class Edge(BaseModel):
    source: str
    target: str
    relation: Relation = Relation.LEADS_TO
    condition: str = Field(default="", description="When this transition applies (TRIGGERS)")
    guidance: str = ""
    pitfalls: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _no_self_loop(self) -> "Edge":
        if self.source == self.target:
            raise ValueError(f"self-loop on {self.source}")
        return self

    @property
    def is_prerequisite(self) -> bool:
        return self.relation in PREREQUISITE_RELATIONS


class Provenance(BaseModel):
    source: str = Field(default="manual", description="manual | llm_draft | demos | refiner")
    model: Optional[str] = None
    created_at: Optional[str] = None
    notes: List[str] = Field(default_factory=list)


class TaskGraph(BaseModel):
    task_id: str
    name: str
    version: str = "0.1.0"
    domain: str = ""
    description: str = ""
    objects: List[ObjectSpec] = Field(default_factory=list)
    initial_state: List[Predicate] = Field(
        default_factory=list, description="Predicates true at Start (pre-satisfied)"
    )
    goal: List[Predicate] = Field(default_factory=list, description="Must hold at End")
    nodes: List[Node]
    edges: List[Edge]
    provenance: Provenance = Field(default_factory=Provenance)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # ----- accessors -----------------------------------------------------------------
    @property
    def node_map(self) -> Dict[str, Node]:
        return {n.id: n for n in self.nodes}

    @property
    def object_map(self) -> Dict[str, ObjectSpec]:
        return {o.id: o for o in self.objects}

    @property
    def start(self) -> Node:
        return next(n for n in self.nodes if n.kind == NodeKind.START)

    @property
    def end(self) -> Node:
        return next(n for n in self.nodes if n.kind == NodeKind.END)

    @property
    def step_ids(self) -> List[str]:
        return [n.id for n in self.nodes if n.is_step]

    def prerequisite_edges(self) -> List[Edge]:
        return [e for e in self.edges if e.is_prerequisite]

    def correction_edges(self) -> List[Edge]:
        return [e for e in self.edges if e.relation == Relation.CORRECTS]

    def substitutes_for(self, node_id: str, object_id: str) -> set:
        out: set = set()
        node = self.node_map.get(node_id)
        if node and object_id in node.allowed_substitutes:
            out.update(node.allowed_substitutes[object_id])
        obj = self.object_map.get(object_id)
        if obj:
            out.update(obj.substitutes)
        return out

    @model_validator(mode="after")
    def _basic_shape(self) -> "TaskGraph":
        starts = [n for n in self.nodes if n.kind == NodeKind.START]
        ends = [n for n in self.nodes if n.kind == NodeKind.END]
        if len(starts) != 1 or len(ends) != 1:
            raise ValueError(
                f"graph must have exactly one start and one end node "
                f"(got {len(starts)} start, {len(ends)} end)"
            )
        ids = [n.id for n in self.nodes]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate node ids: {dupes}")
        return self
