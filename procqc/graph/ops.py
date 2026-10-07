"""Graph operations consumed by the verifiers.

* ``dag`` / ``ancestors`` / ``descendants`` / ``is_order_independent``
* ``executable_set`` — RegulAR's E_t: steps whose required predecessors are complete
* ``topological_importance`` / ``impact_score`` — RegulAR's phi(a) and I_t
* ``verify_sequence`` — symbolic replay of an observed step sequence against the
  graph: flags omission-of-prerequisite, misordering, off-graph addition,
  excess repetition, correction (via CORRECTS back-edges), unmet preconditions,
  early termination and unmet goal. This is the symbolic half of the Graph Verifier.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set

import networkx as nx

from procqc.graph.schema import Predicate, TaskGraph


# --------------------------------------------------------------------------------------
# Basic structure
# --------------------------------------------------------------------------------------
def dag(g: TaskGraph) -> nx.DiGraph:
    d = nx.DiGraph()
    d.add_nodes_from(n.id for n in g.nodes)
    d.add_edges_from((e.source, e.target) for e in g.prerequisite_edges())
    return d


def ancestors(g: TaskGraph, node_id: str) -> Set[str]:
    return set(nx.ancestors(dag(g), node_id))


def descendants(g: TaskGraph, node_id: str) -> Set[str]:
    return set(nx.descendants(dag(g), node_id))


def is_order_independent(g: TaskGraph, a: str, b: str) -> bool:
    """Boundary rule 3.A: permissible order variation iff no path either way."""
    d = dag(g)
    return not (nx.has_path(d, a, b) or nx.has_path(d, b, a))


def required_predecessors(g: TaskGraph, node_id: str) -> Set[str]:
    """Direct prerequisite predecessors that are neither optional nor conditional."""
    d = dag(g)
    nm = g.node_map
    return {
        p for p in d.predecessors(node_id)
        if not nm[p].optional and nm[p].conditional_on is None and p != g.start.id
    }


def transitive_required_predecessors(g: TaskGraph, node_id: str) -> Set[str]:
    nm = g.node_map
    return {
        a for a in ancestors(g, node_id)
        if nm[a].is_step and not nm[a].optional and nm[a].conditional_on is None
    }


# --------------------------------------------------------------------------------------
# Predicate semantics derived from graph structure (no per-task authoring)
# --------------------------------------------------------------------------------------
HOLD_TOKENS = {"grasp", "grasped", "grasping", "isgrasped", "inhand", "held", "holding", "hold", "holds", "gripped",
               "grip", "carried", "carrying", "hasgrasped"}
PLACE_TOKENS = {"placed", "inserted", "attached", "seated", "latched", "docked", "stowed", "mounted", "filled",
                "loaded", "deposited", "installed", "fitted"}


def _tokens(name: str) -> List[str]:
    import re as _re
    return [t.lower() for t in _re.findall(r"[A-Z][a-z0-9]*|[a-z0-9]+", name)]


def is_repeated_step(g: TaskGraph, node_id: str) -> bool:
    """A step that may legitimately run several times: permitted_repeats > 1 or part of a CORRECTS cycle."""
    n = g.node_map.get(node_id)
    if n is None:
        return False
    return n.permitted_repeats > 1 or any(node_id in (e.source, e.target) for e in g.correction_edges())


def infer_scope(g: TaskGraph, pred: Predicate, node_id: Optional[str], role: str) -> str:
    """instance | cumulative | global. Explicit `scope` wins; otherwise:
    effects/preconditions of a repeated step -> instance (the object handled in THIS execution);
    goal predicates -> cumulative; everything else -> global."""
    if pred.scope:
        return pred.scope
    if role == "goal":
        return "cumulative"
    if role in ("effect", "precondition") and node_id and is_repeated_step(g, node_id):
        return "instance"
    return "global"


def _is_hold(name: str) -> bool:
    toks = _tokens(name)
    joined = "".join(toks)
    return any(t in HOLD_TOKENS for t in toks) or joined.startswith("inhand") or "inhand" in joined


def _is_placement(name: str) -> bool:
    toks = _tokens(name)
    if not toks or _is_hold(name):
        return False
    # In*/On*/At* spatial relations (InHolder, OnTable, InBasket, InContainer) or explicit placement verbs
    return toks[0] in ("in", "on", "at", "inside") or any(t in PLACE_TOKENS for t in toks)


def transfer_of(g: TaskGraph, node_id: str) -> Optional[Dict[str, Predicate]]:
    """If the step is a TRANSFER (releases something it held and places/attaches it somewhere),
    return {"release": <hold predicate turning False>, "placement": <placement predicate turning True>}.
    Detected from effect names/values only, so it applies to any task graph."""
    n = g.node_map.get(node_id)
    if n is None:
        return None
    release = next((e for e in n.effects if e.value is False and _is_hold(e.name)), None)
    placement = next((e for e in n.effects if e.value is True and _is_placement(e.name)), None)
    if release is None or placement is None:
        return None
    return {"release": release, "placement": placement}


# --------------------------------------------------------------------------------------
# Executable set and impact (RegulAR)
# --------------------------------------------------------------------------------------
def executable_set(g: TaskGraph, completed: Iterable[str]) -> Set[str]:
    """Steps that may legitimately start now.

    A step is executable when every required (non-optional, unconditional) direct
    predecessor has been completed and it has not exhausted permitted_repeats.
    Optional predecessors never block. START counts as completed.
    """
    done = Counter(completed)
    d = dag(g)
    nm = g.node_map
    out: Set[str] = set()
    for n in g.nodes:
        if not n.is_step:
            continue
        if done[n.id] >= n.permitted_repeats:
            continue
        preds = [p for p in d.predecessors(n.id) if p != g.start.id]
        if all(done[p] > 0 or nm[p].optional or nm[p].conditional_on is not None for p in preds):
            out.add(n.id)
    return out


def end_reachable(g: TaskGraph, completed: Iterable[str]) -> List[str]:
    """Return the list of still-missing steps that block a valid END (empty = may end)."""
    done = set(completed)
    nm = g.node_map
    missing = [
        n.id for n in g.nodes
        if n.is_step and not n.optional and n.conditional_on is None and n.id not in done
    ]
    # mandatory_terminal nodes are already non-optional; keep the order stable
    return sorted(missing, key=lambda x: (not nm[x].mandatory_terminal, x))


def topological_importance(g: TaskGraph, node_id: str, completed: Iterable[str],
                           alpha: float = 0.5) -> float:
    """RegulAR phi(a) = alpha*|desc(a)|/max_b|desc(b)| + (1-alpha)*dist(a,S_done)/max_b dist(b,S_done).

    dist(a, S_done) = shortest path length from the completed frontier to a (steps only).
    """
    d = dag(g)
    steps = g.step_ids
    if node_id not in steps:
        return 0.0
    desc = {s: len([x for x in nx.descendants(d, s) if x in steps]) for s in steps}
    max_desc = max(desc.values()) or 1
    done = set(completed) | {g.start.id}
    dist: Dict[str, float] = {}
    for s in steps:
        best = None
        for src in done:
            if src in d and nx.has_path(d, src, s):
                L = nx.shortest_path_length(d, src, s)
                best = L if best is None else min(best, L)
        dist[s] = float(best if best is not None else len(steps))
    max_dist = max(dist.values()) or 1.0
    return alpha * desc[node_id] / max_desc + (1 - alpha) * dist[node_id] / max_dist


def impact_score(g: TaskGraph, skipped: Iterable[str], completed: Iterable[str],
                 skip_risk: Optional[Dict[str, float]] = None) -> float:
    """RegulAR I_t = 1 - prod_{a in U_t} (1 - phi(a) * rho(a)). rho defaults to 1."""
    prod = 1.0
    for a in skipped:
        phi = topological_importance(g, a, completed)
        rho = (skip_risk or {}).get(a, 1.0)
        prod *= (1.0 - phi * rho)
    return 1.0 - prod


# --------------------------------------------------------------------------------------
# Symbolic sequence verification
# --------------------------------------------------------------------------------------
@dataclass
class Violation:
    index: int  # position in the observed sequence (-1 for end-of-episode checks)
    step: Optional[str]
    kind: str  # omission | misordering | addition_offgraph | addition_repeat | correction |
    #            precondition | early_termination | goal_unmet
    detail: str
    missing: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        where = f"@{self.index}" if self.index >= 0 else "@end"
        return f"{self.kind}{where} {self.step or ''}: {self.detail}"


@dataclass
class VerifyResult:
    violations: List[Violation]
    completed: List[str]
    final_state: Dict[str, bool]
    impact: float

    @property
    def ok(self) -> bool:
        return not self.violations

    def by_kind(self) -> Dict[str, int]:
        c: Counter = Counter(v.kind for v in self.violations)
        return dict(c)


def _apply(state: Dict[str, bool], preds: Iterable[Predicate]) -> None:
    for p in preds:
        state[p.key] = p.value


def verify_sequence(g: TaskGraph, observed: Sequence[str],
                    initial_state: Optional[Dict[str, bool]] = None,
                    check_predicates: bool = True) -> VerifyResult:
    """Replay an observed sequence of step ids against the graph.

    Classification (mirrors the taxonomy):
    * step not in graph                         -> addition_offgraph
    * step executed more than permitted_repeats -> addition_repeat, unless a CORRECTS
      back-edge from the previous step targets it (or an ancestor of it) -> correction
    * step not executable because a required predecessor is missing:
        - predecessor appears later in the sequence -> misordering
        - predecessor never appears                 -> omission
    * preconditions unmet in the symbolic state -> precondition (state-level evidence)
    * non-optional steps missing at the end     -> early_termination (mandatory_terminal
      first) ; goal predicates unmet            -> goal_unmet
    """
    nm = g.node_map
    d = dag(g)
    corrections = {(e.source, e.target) for e in g.correction_edges()}
    state: Dict[str, bool] = {p.key: p.value for p in g.initial_state}
    if initial_state:
        state.update(initial_state)

    done: Counter = Counter()
    completed: List[str] = []
    violations: List[Violation] = []
    future = Counter(observed)
    prev: Optional[str] = None

    for i, s in enumerate(observed):
        future[s] -= 1
        if s not in nm or not nm[s].is_step:
            violations.append(Violation(i, s, "addition_offgraph", "step is not in the task graph"))
            prev = s
            continue
        node = nm[s]

        # repeats / corrections
        if done[s] >= node.permitted_repeats:
            is_corr = prev is not None and (
                (prev, s) in corrections
                or any(t == s or nx.has_path(d, s, t) for (src, t) in corrections if src == prev)
            )
            kind = "correction" if is_corr else "addition_repeat"
            violations.append(Violation(i, s, kind,
                                        f"executed {done[s] + 1}x, permitted {node.permitted_repeats}"
                                        + (" (CORRECTS back-edge)" if is_corr else "")))
        # prerequisites
        req = required_predecessors(g, s)
        missing = sorted(p for p in req if done[p] == 0)
        if missing:
            later = [p for p in missing if future[p] > 0]
            never = [p for p in missing if future[p] == 0]
            if later:
                violations.append(Violation(i, s, "misordering",
                                            f"executed before prerequisite(s) {later}", missing=later))
            if never:
                violations.append(Violation(i, s, "omission",
                                            f"prerequisite(s) {never} never executed", missing=never))
        # symbolic preconditions
        if check_predicates:
            unmet = [str(p) for p in node.preconditions if state.get(p.key) is not None and
                     state.get(p.key) != p.value]
            if unmet:
                violations.append(Violation(i, s, "precondition", f"unmet in symbolic state: {unmet}"))
        _apply(state, node.effects)
        done[s] += 1
        completed.append(s)
        prev = s

    # end of episode
    missing_end = end_reachable(g, completed)
    if missing_end:
        # A missing mandatory_terminal step is reported as EARLY TERMINATION: from the step
        # sequence alone, "operator stopped before the terminal step" and "operator skipped the
        # terminal step" are indistinguishable (both leave it pending at the end). The effect
        # verifier / adjudicator can refine this with timing (recording continued long after the
        # last step) or with the terminal state visible in the final frames.
        term = [m for m in missing_end if nm[m].mandatory_terminal]
        other = [m for m in missing_end if not nm[m].mandatory_terminal]
        if term:
            violations.append(Violation(-1, None, "early_termination",
                                        f"mandatory terminal step(s) not completed: {term}", missing=term))
        # missing steps never flagged as someone's prerequisite are omissions
        already = {m for v in violations for m in v.missing}
        rest = [m for m in other if m not in already]
        if rest:
            violations.append(Violation(-1, None, "omission",
                                        f"required step(s) never executed: {rest}", missing=rest))
    if check_predicates:
        unmet_goal = [str(p) for p in g.goal if state.get(p.key) != p.value]
        if unmet_goal:
            violations.append(Violation(-1, None, "goal_unmet", f"goal predicates unmet: {unmet_goal}"))

    skipped = sorted({m for v in violations for m in v.missing})
    imp = impact_score(g, skipped, completed) if skipped else 0.0
    return VerifyResult(violations=violations, completed=completed, final_state=state, impact=imp)
