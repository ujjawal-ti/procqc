"""YAML / JSON load-save and a Mermaid renderer for task graphs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Union

import yaml

from procqc.graph.schema import Relation, TaskGraph

PathLike = Union[str, Path]


def load_graph(path: PathLike) -> TaskGraph:
    p = Path(path)
    text = p.read_text()
    data = json.loads(text) if p.suffix.lower() == ".json" else yaml.safe_load(text)
    return TaskGraph.model_validate(data)


def graph_to_dict(g: TaskGraph) -> dict:
    return g.model_dump(mode="json", exclude_none=True, exclude_defaults=False)


def save_graph(g: TaskGraph, path: PathLike) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = graph_to_dict(g)
    if p.suffix.lower() == ".json":
        p.write_text(json.dumps(data, indent=2))
    else:
        p.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100))


_STYLE = {
    Relation.LEADS_TO: "-->",
    Relation.TRIGGERS: "-. cond .->",
    Relation.PROVIDES_INPUT_FOR: "==>",
    Relation.CONVERGES_TO: "-->",
    Relation.CORRECTS: "-. corrects .->",
}


def to_mermaid(g: TaskGraph) -> str:
    """Render as a Mermaid flowchart (paste into any Markdown viewer / Notion)."""
    lines = ["flowchart TD"]
    for n in g.nodes:
        label = n.name.replace('"', "'")
        if n.kind.value == "start":
            lines.append(f'    {n.id}(["{label}"])')
        elif n.kind.value == "end":
            lines.append(f'    {n.id}(["{label}"])')
        elif n.kind.value == "check":
            lines.append(f'    {n.id}{{{{"{label}"}}}}')
        else:
            flags = []
            if n.optional:
                flags.append("optional")
            if n.mandatory_terminal:
                flags.append("terminal")
            if n.permitted_repeats > 1:
                flags.append(f"x{n.permitted_repeats}")
            suffix = f"<br/><i>{', '.join(flags)}</i>" if flags else ""
            lines.append(f'    {n.id}["{label}{suffix}"]')
    for e in g.edges:
        arrow = _STYLE.get(e.relation, "-->")
        if e.relation == Relation.TRIGGERS and e.condition:
            cond = e.condition.replace('"', "'")[:40]
            arrow = f"-. {cond} .->"
        lines.append(f"    {e.source} {arrow} {e.target}")
    return "\n".join(lines)
