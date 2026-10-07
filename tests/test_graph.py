"""Task graph: schema, linter, operations, I/O, drafter schema (no network)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from procqc.graph import ops
from procqc.graph.io import graph_to_dict, load_graph, save_graph, to_mermaid
from procqc.graph.linter import has_errors, lint
from procqc.graph.schema import Edge, Node, NodeKind, ObjectSpec, Predicate, TaskGraph

EX = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture
def g() -> TaskGraph:
    return load_graph(EX / "pipette_transfer.yaml")


@pytest.fixture
def demos():
    rows = [json.loads(line) for line in open(EX / "pipette_demos.jsonl") if line.strip()]
    return [r["steps"] for r in rows]


# ----- schema ---------------------------------------------------------------------------
def test_predicate_parse():
    p = Predicate.parse("!IsOpen(vial_src)", checker="vlm_effect")
    assert p.name == "IsOpen" and p.args == ["vial_src"] and p.value is False
    assert Predicate.parse("HasTip(pipette)=False").value is False
    assert Predicate.parse("IsFilled(vial_dst)").key == "IsFilled(vial_dst)"


def test_schema_rejects_two_starts():
    with pytest.raises(ValueError):
        TaskGraph(task_id="t", name="t",
                  nodes=[Node(id="start", name="S", kind=NodeKind.START),
                         Node(id="start2", name="S", kind=NodeKind.START),
                         Node(id="end", name="E", kind=NodeKind.END)],
                  edges=[])


def test_schema_rejects_optional_terminal():
    with pytest.raises(ValueError):
        Node(id="x", name="x", optional=True, mandatory_terminal=True)


# ----- example graph is clean ------------------------------------------------------------
def test_example_lints_clean(g):
    issues = lint(g)
    assert not has_errors(issues), "\n".join(str(i) for i in issues)
    # W015 is impossible here: every predicate has a checker
    assert not [i for i in issues if i.code == "W015"]


def test_roundtrip(g, tmp_path):
    p = tmp_path / "g.yaml"
    save_graph(g, p)
    g2 = load_graph(p)
    assert graph_to_dict(g2) == graph_to_dict(g)
    save_graph(g, tmp_path / "g.json")
    assert graph_to_dict(load_graph(tmp_path / "g.json")) == graph_to_dict(g)


def test_mermaid(g):
    m = to_mermaid(g)
    assert m.startswith("flowchart TD") and "s04_aspirate" in m and "corrects" in m


# ----- linter catches structural problems ------------------------------------------------
def _tiny(edges):
    nodes = [Node(id="start", name="S", kind=NodeKind.START),
             Node(id="a", name="A", description="a", effect_description="x"),
             Node(id="b", name="B", description="b", effect_description="x"),
             Node(id="end", name="E", kind=NodeKind.END)]
    return TaskGraph(task_id="t", name="t", nodes=nodes, edges=[Edge(**e) for e in edges])


def test_lint_cycle():
    g = _tiny([{"source": "start", "target": "a"}, {"source": "a", "target": "b"},
               {"source": "b", "target": "a"}, {"source": "b", "target": "end"}])
    codes = {i.code for i in lint(g)}
    assert "E005" in codes


def test_lint_unreachable_and_no_end():
    g = _tiny([{"source": "start", "target": "a"}, {"source": "a", "target": "end"}])
    codes = {i.code for i in lint(g)}
    assert {"E006", "E007"} <= codes  # b is disconnected


def test_lint_dangling_and_bad_corrects():
    g = _tiny([{"source": "start", "target": "a"}, {"source": "a", "target": "b"},
               {"source": "b", "target": "end"},
               {"source": "a", "target": "b", "relation": "CORRECTS"}])  # forward "correction"
    codes = {i.code for i in lint(g)}
    assert "E008" in codes
    with pytest.raises(ValueError):
        Edge(source="a", target="a")


def test_lint_precondition_support_warning():
    nodes = [Node(id="start", name="S", kind=NodeKind.START),
             Node(id="a", name="A", description="a", effect_description="x",
                  preconditions=[Predicate(name="IsOpen", args=["v"], checker="vlm_effect")]),
             Node(id="end", name="E", kind=NodeKind.END)]
    g = TaskGraph(task_id="t", name="t", nodes=nodes,
                  edges=[Edge(source="start", target="a"), Edge(source="a", target="end")])
    codes = {i.code for i in lint(g)}
    assert "W009" in codes and "W013" in codes


# ----- ops -------------------------------------------------------------------------------
def test_executable_set_progression(g):
    e0 = ops.executable_set(g, [])
    assert e0 == {"s01_pick_pipette", "s03_uncap_source", "s05_uncap_dest"}
    e1 = ops.executable_set(g, ["s01_pick_pipette"])
    assert "s02_attach_tip" in e1 and "s04_aspirate" not in e1
    e2 = ops.executable_set(g, ["s01_pick_pipette", "s02_attach_tip", "s03_uncap_source"])
    assert "s04_aspirate" in e2


def test_order_independence(g):
    assert ops.is_order_independent(g, "s03_uncap_source", "s05_uncap_dest")
    assert not ops.is_order_independent(g, "s03_uncap_source", "s04_aspirate")


def test_verify_clean_demos(g, demos):
    for seq in demos:
        res = ops.verify_sequence(g, seq)
        assert res.ok, f"{seq}\n" + "\n".join(str(v) for v in res.violations)


def test_verify_omission(g):
    seq = ["s01_pick_pipette", "s02_attach_tip", "s04_aspirate", "s05_uncap_dest", "s06_dispense",
           "s07_eject_tip", "s09_recap_dest", "s10_return_pipette"]  # never uncaps / recaps source
    res = ops.verify_sequence(g, seq)
    kinds = res.by_kind()
    assert kinds.get("omission", 0) >= 1 and kinds.get("precondition", 0) >= 1
    assert any("s03_uncap_source" in v.missing for v in res.violations)
    assert kinds.get("early_termination", 0) >= 1  # s08_recap_source is mandatory_terminal
    assert 0 < res.impact <= 1


def test_verify_misordering(g):
    seq = ["s01_pick_pipette", "s02_attach_tip", "s04_aspirate", "s03_uncap_source", "s05_uncap_dest",
           "s06_dispense", "s07_eject_tip", "s08_recap_source", "s09_recap_dest", "s10_return_pipette"]
    res = ops.verify_sequence(g, seq)
    mis = [v for v in res.violations if v.kind == "misordering"]
    assert mis and mis[0].step == "s04_aspirate" and "s03_uncap_source" in mis[0].missing
    assert not [v for v in res.violations if v.kind == "omission"]


def test_verify_addition_and_correction(g):
    base = ["s01_pick_pipette", "s02_attach_tip", "s03_uncap_source", "s04_aspirate", "s05_uncap_dest",
            "s06_dispense", "s07_eject_tip", "s08_recap_source", "s09_recap_dest", "s10_return_pipette"]
    # off-graph action
    res = ops.verify_sequence(g, base[:3] + ["wipe_bench"] + base[3:])
    assert res.by_kind().get("addition_offgraph") == 1
    # repeat without a CORRECTS edge -> addition_repeat
    res = ops.verify_sequence(g, base[:4] + ["s04_aspirate"] + base[4:])
    assert res.by_kind().get("addition_repeat") == 1
    # eject tip then re-attach (CORRECTS edge s07 -> s02) -> correction, not repeat
    seq = ["s01_pick_pipette", "s02_attach_tip", "s07_eject_tip", "s02_attach_tip", "s03_uncap_source",
           "s04_aspirate", "s05_uncap_dest", "s06_dispense", "s07_eject_tip", "s08_recap_source",
           "s09_recap_dest", "s10_return_pipette"]
    res = ops.verify_sequence(g, seq)
    kinds = res.by_kind()
    assert kinds.get("correction", 0) >= 1
    assert kinds.get("addition_repeat", 0) == 0 or kinds.get("correction", 0) >= 1


def test_verify_early_termination(g):
    seq = ["s01_pick_pipette", "s02_attach_tip", "s03_uncap_source", "s04_aspirate", "s05_uncap_dest",
           "s06_dispense"]  # recording stopped
    res = ops.verify_sequence(g, seq)
    kinds = res.by_kind()
    assert kinds.get("early_termination") == 1 and kinds.get("goal_unmet") == 1
    et = next(v for v in res.violations if v.kind == "early_termination")
    assert set(et.missing) == {"s08_recap_source", "s09_recap_dest", "s10_return_pipette"}


def test_impact_monotone(g):
    done = ["s01_pick_pipette", "s02_attach_tip"]
    early = ops.topological_importance(g, "s03_uncap_source", done)
    late = ops.topological_importance(g, "s10_return_pipette", done)
    assert early > late  # uncapping unlocks more downstream work


def test_lint_terminal_parallel_branches_ok(g):
    # three required terminal steps on parallel branches to END must NOT trigger W011
    assert not [i for i in lint(g) if i.code == "W011"]


def test_lint_terminal_behind_optional_warns():
    nodes = [Node(id="start", name="S", kind=NodeKind.START),
             Node(id="a", name="A", description="a", effect_description="x", optional=True),
             Node(id="b", name="B", description="b", effect_description="x", mandatory_terminal=True),
             Node(id="end", name="E", kind=NodeKind.END)]
    g2 = TaskGraph(task_id="t", name="t", nodes=nodes,
                   edges=[Edge(source="start", target="a"), Edge(source="a", target="b"),
                          Edge(source="b", target="end")])
    assert [i for i in lint(g2) if i.code == "W011"]


# ----- draft schema (no network) ---------------------------------------------------------
def test_llm_schema_requires_content_fields():
    from procqc.graph.draft import _llm_schema, _REQUIRED_BY_MODEL
    s = _llm_schema()
    assert set(_REQUIRED_BY_MODEL["TaskGraph"]) <= set(s["required"])
    assert "provenance" not in s["properties"]
    node = s["$defs"]["Node"]
    assert {"effects", "preconditions", "mandatory_terminal", "effect_description"} <= set(node["required"])
    assert "checker" in s["$defs"]["Predicate"]["required"]
    # a graph produced under this schema must still validate against TaskGraph
    minimal = {"task_id": "t", "name": "t", "domain": "", "description": "", "objects": [],
               "initial_state": [], "goal": [],
               "nodes": [{"id": "start", "name": "S", "kind": "start"}, {"id": "end", "name": "E", "kind": "end"}],
               "edges": [{"source": "start", "target": "end", "relation": "LEADS_TO", "condition": ""}]}
    TaskGraph.model_validate(minimal)


def test_normalize_moves_end_preconditions_and_declares_objects():
    from procqc.graph.draft import _normalize
    data = {"task_id": "t", "name": "t", "objects": [{"id": "pipette", "substitutes": ["p1000"]}],
            "goal": [], "initial_state": [],
            "nodes": [{"id": "start", "name": "S", "kind": "start", "effects": [{"name": "A", "args": ["x"]}]},
                      {"id": "s01_a", "name": "a", "kind": "step", "tools": ["pipette"], "target_objects": ["vial"]},
                      {"id": "end", "name": "E", "kind": "end",
                       "preconditions": [{"name": "Done", "args": ["vial"], "value": True}]}],
            "edges": [{"source": "start", "target": "s01_a"}, {"source": "s01_a", "target": "end"}]}
    out = _normalize(data)
    assert out["goal"] and out["goal"][0]["name"] == "Done"
    assert out["initial_state"] and out["initial_state"][0]["name"] == "A"
    assert not out["nodes"][2].get("preconditions") and not out["nodes"][0].get("effects")
    assert {"p1000", "vial", "x"} <= {o["id"] for o in out["objects"]}
    TaskGraph.model_validate(out)


def test_lint_w020_signal_checker_on_visual_state():
    from procqc.graph.linter import signal_checker_mismatch
    assert signal_checker_mismatch("IsOpen", "proprio_pose")
    assert signal_checker_mismatch("Coiled", "ft_contact")
    assert signal_checker_mismatch("Grasped", "ft_contact") is None
    assert signal_checker_mismatch("InHolder", "proprio_pose") is None
    assert signal_checker_mismatch("IsOpen", "vlm_effect") is None
    nodes = [Node(id="start", name="S", kind=NodeKind.START),
             Node(id="a", name="A", description="a", effect_description="x",
                  effects=[Predicate(name="IsOpen", args=["d"], checker="proprio_pose")]),
             Node(id="end", name="E", kind=NodeKind.END)]
    g2 = TaskGraph(task_id="t", name="t", nodes=nodes, objects=[ObjectSpec(id="d", name="drawer")],
                   edges=[Edge(source="start", target="a"), Edge(source="a", target="end")])
    assert "W020" in {i.code for i in lint(g2)}
