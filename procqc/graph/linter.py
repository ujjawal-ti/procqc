"""Structural linter for task graphs.

Mirrors the structural verification step of Procedural Graphs (acyclicity,
connectivity, no dangling references, non-empty attributes, relation vocabulary)
plus QC-specific checks (predicate support, terminal nodes on every path,
correction edges point backwards, substitutes reference declared objects).

Errors (E*) make the graph unusable by the verifier; warnings (W*) are quality
issues the LLM refiner / a human should look at.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import networkx as nx

from procqc.graph.schema import NodeKind, Relation, TaskGraph


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass
class LintIssue:
    code: str
    severity: Severity
    message: str
    node: Optional[str] = None
    edge: Optional[str] = None  # "source->target"

    def __str__(self) -> str:
        where = f" [{self.node or self.edge}]" if (self.node or self.edge) else ""
        return f"{self.severity.value.upper()} {self.code}{where}: {self.message}"


# What each signal checker can actually attest. A predicate name that carries none of these words
# is a visual object state (open/closed, attached, coiled, filled, placed) and needs a vision key.
_SIGNAL_VOCAB = {
    "gripper_width": ("grasp", "held", "hold", "inhand", "gripped", "release"),
    "ft_contact": ("grasp", "held", "hold", "inhand", "contact", "touch", "seated", "latched", "pressed",
                   "engaged", "inserted", "release"),
    "proprio_pose": ("pose", "position", "at", "above", "over", "near", "home", "holder", "dock", "retract",
                     "reach", "raised", "lowered"),
    "kinematic_idle": ("idle", "still", "settled", "stationary", "paused"),
}


def signal_checker_mismatch(name: str, checker: Optional[str]) -> Optional[str]:
    """Return a message when a signal-only checker is assigned to a predicate whose name does not
    describe anything that signal can measure (e.g. IsOpen(drawer) via proprio_pose)."""
    if checker not in _SIGNAL_VOCAB:
        return None
    low = name.lower()
    if any(w in low for w in _SIGNAL_VOCAB[checker]):
        return None
    return (f"'{name}' looks like a visual object state but is assigned the signal-only checker "
            f"'{checker}'; use vlm_effect/detector (signal checkers attest {', '.join(_SIGNAL_VOCAB[checker][:4])}...)")


def _dag(g: TaskGraph) -> nx.DiGraph:
    d = nx.DiGraph()
    d.add_nodes_from(n.id for n in g.nodes)
    d.add_edges_from((e.source, e.target) for e in g.prerequisite_edges())
    return d


def lint(g: TaskGraph, known_checkers: Optional[set] = None) -> List[LintIssue]:
    issues: List[LintIssue] = []
    err = lambda code, msg, **kw: issues.append(LintIssue(code, Severity.ERROR, msg, **kw))  # noqa: E731
    warn = lambda code, msg, **kw: issues.append(LintIssue(code, Severity.WARNING, msg, **kw))  # noqa: E731

    ids = set(g.node_map)
    obj_ids = set(g.object_map)

    # E003 dangling edge references
    for e in g.edges:
        for ref in (e.source, e.target):
            if ref not in ids:
                err("E003", f"edge references unknown node {ref!r}", edge=f"{e.source}->{e.target}")
    valid_edges = [e for e in g.edges if e.source in ids and e.target in ids]

    # E004 edges into start / out of end
    for e in valid_edges:
        if e.is_prerequisite:
            if e.target == g.start.id:
                err("E004", "prerequisite edge into START", edge=f"{e.source}->{e.target}")
            if e.source == g.end.id:
                err("E004", "prerequisite edge out of END", edge=f"{e.source}->{e.target}")

    # E005 cycles among prerequisite edges
    dag = _dag(g)
    if not nx.is_directed_acyclic_graph(dag):
        cyc = nx.find_cycle(dag)
        err("E005", "prerequisite edges form a cycle: " + " -> ".join(u for u, _ in cyc) + f" -> {cyc[0][0]}")
        return issues  # further reachability checks are meaningless

    # E006 reachability from start; E007 end reachable from every node
    reach = nx.descendants(dag, g.start.id) | {g.start.id}
    for n in g.nodes:
        if n.id not in reach:
            err("E006", "not reachable from START via prerequisite edges", node=n.id)
    anc_end = nx.ancestors(dag, g.end.id) | {g.end.id}
    for n in g.nodes:
        if n.id not in anc_end:
            err("E007", "END not reachable from this node", node=n.id)

    # E008 CORRECTS must be a back-edge: target is an ancestor of source (or source itself's ancestor)
    for e in g.correction_edges():
        if e.source in ids and e.target in ids:
            if e.target not in nx.ancestors(dag, e.source):
                err("E008", "CORRECTS edge must point to an ancestor (a recovery goes backwards)",
                    edge=f"{e.source}->{e.target}")

    # W016 TRIGGERS without condition
    for e in valid_edges:
        if e.relation == Relation.TRIGGERS and not e.condition.strip():
            warn("W016", "TRIGGERS edge has no condition text", edge=f"{e.source}->{e.target}")

    # W010 empty descriptions on steps
    for n in g.nodes:
        if n.is_step:
            if not n.description.strip():
                warn("W010", "step has no description", node=n.id)
            if not n.effect_description.strip() and not n.effects:
                warn("W010", "step has neither effects nor effect_description (unverifiable)", node=n.id)

    # W013 undeclared objects; W017 substitutes reference undeclared objects
    for n in g.nodes:
        for oid in list(n.target_objects) + list(n.tools):
            if oid not in obj_ids:
                warn("W013", f"references undeclared object {oid!r}", node=n.id)
        for p in list(n.preconditions) + list(n.effects):
            for a in p.args:
                if a not in obj_ids:
                    warn("W013", f"predicate {p.key} references undeclared object {a!r}", node=n.id)
        for oid, subs in n.allowed_substitutes.items():
            for s in [oid] + list(subs):
                if s not in obj_ids:
                    warn("W017", f"allowed_substitutes references undeclared object {s!r}", node=n.id)
    for o in g.objects:
        for s in o.substitutes:
            if s not in obj_ids:
                warn("W017", f"object {o.id} lists undeclared substitute {s!r}")

    # W014 unknown checker keys (only if a registry is given); W015 unverifiable predicates;
    # W020 visual state predicate assigned a signal-only checker (once per node/predicate/checker)
    seen_w020: set = set()
    for n in g.nodes:
        for p in list(n.preconditions) + list(n.effects):
            if p.checker is None:
                warn("W015", f"predicate {p.key} has no checker (cannot be auto-verified)", node=n.id)
            elif known_checkers is not None and p.checker not in known_checkers:
                warn("W014", f"predicate {p.key} uses unknown checker {p.checker!r}", node=n.id)
            msg = signal_checker_mismatch(p.name, p.checker)
            if msg and (n.id, p.key, p.checker) not in seen_w020:
                seen_w020.add((n.id, p.key, p.checker))
                warn("W020", f"predicate {p.key}: {msg}", node=n.id)
    for p in list(g.initial_state) + list(g.goal):
        msg = signal_checker_mismatch(p.name, p.checker)
        if msg and ("__graph__", p.key, p.checker) not in seen_w020:
            seen_w020.add(("__graph__", p.key, p.checker))
            warn("W020", f"initial_state/goal predicate {p.key}: {msg}")

    # W009 precondition support: every precondition must be established by an ancestor's
    # effect or by initial_state (otherwise the verifier will flag every episode).
    initial = {p.key: p.value for p in g.initial_state}
    for n in g.nodes:
        if not n.is_step:
            continue
        anc = nx.ancestors(dag, n.id)
        established = dict(initial)
        for a in anc:
            for eff in g.node_map[a].effects:
                established[eff.key] = eff.value  # last writer wins is approximate; fine for lint
        for pre in n.preconditions:
            if pre.key not in established:
                warn("W009", f"precondition {pre} is never established by any ancestor or initial_state",
                     node=n.id)
            elif established[pre.key] != pre.value and not any(
                eff.key == pre.key and eff.value == pre.value for a in anc for eff in g.node_map[a].effects
            ):
                warn("W009", f"precondition {pre} contradicts every ancestor effect / initial_state",
                     node=n.id)

    # W011 a mandatory_terminal node must always become executable in a valid episode: it needs
    # at least one path from START made only of required (non-optional, unconditional) steps.
    # If every route to it passes through an optional/conditional step, a clean episode that
    # skips that step could never complete it, and every such episode would be flagged.
    required_sub = dag.subgraph(
        [n.id for n in g.nodes if not (n.is_step and (n.optional or n.conditional_on is not None))]
    )
    for n in g.nodes:
        if n.mandatory_terminal and n.id in required_sub:
            if not nx.has_path(required_sub, g.start.id, n.id):
                warn("W011", "mandatory_terminal but only reachable through optional/conditional steps; "
                             "clean episodes that skip them can never complete it", node=n.id)

    # W018 goal predicates never established
    established_all = {p.key: p.value for p in g.initial_state}
    for n in g.nodes:
        for eff in n.effects:
            established_all[eff.key] = eff.value
    for gp in g.goal:
        if gp.key not in established_all:
            warn("W018", f"goal predicate {gp} is never established by any node effect")

    # W019 optional node with mandatory_terminal already rejected by schema; warn on isolated CHECK
    for n in g.nodes:
        if n.kind == NodeKind.CHECK and not n.preconditions:
            warn("W019", "CHECK node has no preconditions (what does it verify?)", node=n.id)

    return issues


def has_errors(issues: List[LintIssue]) -> bool:
    return any(i.severity == Severity.ERROR for i in issues)


def format_issues(issues: List[LintIssue]) -> str:
    if not issues:
        return "OK: no issues"
    return "\n".join(str(i) for i in issues)
