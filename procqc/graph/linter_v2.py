"""Checks for version 2 task graphs (`procqc/graph/schema_v2.py`), on top of version 1's linter.

  E101  a repeat block has no end condition (no predicate and no description)
  E102  a step inside a repeat block has a fixed repeat count (it must be UNBOUNDED)
  W101  an SOP sentence is not accounted for by any element (graph element or not_modelled)
  W102  an element's quote is not in the SOP (it was marked inferred)
Version 1's codes (E0xx / W0xx) are unchanged.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional, Tuple

from procqc.graph.linter import LintIssue, Severity, lint
from procqc.graph.schema_v2 import UNBOUNDED, Source, TaskGraphV2

_STOP = {"the", "a", "an", "and", "or", "of", "to", "on", "in", "for", "with", "each", "is", "be", "it", "its",
         "at", "by", "from", "as", "per", "no", "not", "do", "this", "that", "one"}
COVER_MIN = 0.6  # share of a sentence's content words that one quote must contain


def norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", (text or "").lower()).split())


def words(text: str) -> List[str]:
    return [w for w in norm(text).split() if len(w) > 1 and w not in _STOP]


def sentences(sop: str) -> List[str]:
    """SOP sentences to account for: lines split at sentence ends, without list numbers and headings."""
    out = []
    for line in sop.splitlines():
        if line.lstrip().startswith("#"):
            continue  # a markdown heading (the task title)
        line = re.sub(r"^\s*(?:[-*>]+|\d+[.)])\s*", "", line).strip()
        if not line or (line.endswith(":") and len(line.split()) <= 5):
            continue
        for s in re.split(r"(?<=[.!?])\s+", line):
            s = s.strip()
            if len(words(s)) >= 1:
                out.append(s)
    return out


def quote_in_sop(quote: str, sop: str) -> bool:
    q = norm(quote)
    return bool(q) and q in norm(sop)


def sources(g: TaskGraphV2) -> Iterable[Tuple[str, Source]]:
    for o in g.objects:
        yield f"object {o.id}", o.source
    for n in g.nodes:
        if n.is_step:
            yield f"step {n.id}", n.source
    for f in g.starting_state:
        yield "starting_state", f.source
    for b in g.repeat_blocks:
        yield f"repeat block {b.id}", b.source
    for a in g.acceptance:
        yield f"acceptance {a.id}", a.source
    for c in g.constraints:
        yield f"constraint {c.id}", c.source
    if g.scenario:
        yield "scenario", g.scenario.source


def quotes(g: TaskGraphV2) -> List[str]:
    q = [s.quote for _, s in sources(g) if s.quote and not s.inferred] + [m.quote for m in g.not_modelled]
    if g.scenario:
        sc = g.scenario
        q += [f"activity type {sc.activity_type}", f"site id {sc.site_id}", f"location {sc.location}",
              f"scene type {sc.scene_type}", f"country {sc.country}", *[f"{k} {v}" for k, v in sc.other.items()]]
    return q


def covered(sentence: str, qs: List[str]) -> bool:
    w = set(words(sentence))
    if not w:
        return True
    return any(len(w & set(words(q))) >= COVER_MIN * len(w) for q in qs)


def lint_v2(g: TaskGraphV2, sop: str, known_checkers: Optional[set] = None) -> List[LintIssue]:
    issues = lint(g, known_checkers=known_checkers)
    for b in g.repeat_blocks:
        if not b.until and not b.until_description.strip():
            issues.append(LintIssue("E101", Severity.ERROR, f"repeat block {b.id} has no end condition"))
        for s in b.steps:
            if g.node_map[s].permitted_repeats != UNBOUNDED:
                issues.append(LintIssue("E102", Severity.ERROR, f"step in repeat block {b.id} has a fixed repeat count",
                                        node=s))
    qs = quotes(g)
    for s in sentences(sop):
        if not covered(s, qs):
            issues.append(LintIssue("W101", Severity.WARNING, f"SOP sentence not accounted for: {s!r}"))
    for where, src in sources(g):
        if src.inferred and src.quote:
            issues.append(LintIssue("W102", Severity.WARNING, f"{where}: quote not in the SOP, marked inferred: {src.quote!r}"))
    return issues
