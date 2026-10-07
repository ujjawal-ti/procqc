"""Command-line entry point for task graphs.

    python3 -m procqc.graph.cli lint     graph.yaml [--sop sop.md]    # version 2 checks too when --sop is given
    python3 -m procqc.graph.cli render   graph.yaml                   # Mermaid to stdout
    python3 -m procqc.graph.cli verify   graph.yaml s01 s03 s02 ...   # symbolic replay of a step sequence
    python3 -m procqc.graph.cli draft    sop.md out.yaml --task-id X [--domain D] [--model M]   # version 1 graph
    python3 -m procqc.graph.cli draft-v2 sop.md out.yaml --task-id X [--domain D] [--model M]   # version 2 graph
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from procqc.graph import ops
from procqc.graph.io import load_graph, save_graph, to_mermaid
from procqc.graph.linter import format_issues, has_errors, lint


def _cmd_lint(a: argparse.Namespace) -> int:
    if a.sop:
        from procqc.graph.linter_v2 import lint_v2
        from procqc.graph.schema_v2 import load_graph_v2
        issues = lint_v2(load_graph_v2(a.graph), Path(a.sop).read_text())
    else:
        issues = lint(load_graph(a.graph))
    print(format_issues(issues) if issues else "OK: no issues")
    return 1 if has_errors(issues) else 0


def _cmd_render(a: argparse.Namespace) -> int:
    print(to_mermaid(load_graph(a.graph)))
    return 0


def _cmd_verify(a: argparse.Namespace) -> int:
    g = load_graph(a.graph)
    res = ops.verify_sequence(g, a.steps)
    if res.ok:
        print("OK: sequence is consistent with the task graph")
    else:
        for v in res.violations:
            print(v)
        print(f"impact score: {res.impact:.2f}  by_kind: {res.by_kind()}")
    return 0 if res.ok else 1


def _cmd_draft(a: argparse.Namespace) -> int:
    from procqc.graph.draft import draft_graph  # lazy: needs openai + credentials
    g = draft_graph(Path(a.sop).read_text(), task_id=a.task_id, domain=a.domain or "", model=a.model, verbose=True)
    save_graph(g, a.out)
    print(format_issues(lint(g)))
    print(f"wrote {a.out}  ({g.provenance.notes})")
    return 0


def _cmd_draft_v2(a: argparse.Namespace) -> int:
    from procqc.graph.draft_v2 import draft_graph_v2  # lazy: needs openai + credentials
    g, fields, issues = draft_graph_v2(Path(a.sop).read_text(), a.task_id, a.domain, model=a.model, verbose=True)
    save_graph(g, a.out)
    Path(a.out).with_suffix(".extract.json").write_text(json.dumps(fields, indent=1))
    print(format_issues(issues) if issues else "OK: no issues")
    print(f"wrote {a.out} and its field extraction; {g.provenance.notes}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="procqc.graph.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("lint")
    s.add_argument("graph")
    s.add_argument("--sop", default="", help="the SOP the graph was drafted from (version 2 checks)")
    s.set_defaults(fn=_cmd_lint)
    s = sub.add_parser("render")
    s.add_argument("graph")
    s.set_defaults(fn=_cmd_render)
    s = sub.add_parser("verify")
    s.add_argument("graph")
    s.add_argument("steps", nargs="+")
    s.set_defaults(fn=_cmd_verify)
    for name, fn in (("draft", _cmd_draft), ("draft-v2", _cmd_draft_v2)):
        s = sub.add_parser(name)
        s.add_argument("sop")
        s.add_argument("out")
        s.add_argument("--task-id", required=True)
        s.add_argument("--domain", default="")
        s.add_argument("--model", default=None)
        s.set_defaults(fn=fn)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
