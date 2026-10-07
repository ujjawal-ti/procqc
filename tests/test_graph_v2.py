import pytest

from procqc.graph import draft_v2 as DV
from procqc.graph.io import load_graph, save_graph
from procqc.graph.linter_v2 import covered, lint_v2, quote_in_sop, sentences
from procqc.graph.schema_v2 import UNBOUNDED, TaskGraphV2, load_graph_v2

SOP = """Objects:
Parts.
From: Bench. To: Tray.
Constraints / Avoid: Do not drop parts into the tray.
Steps:
1. Pick up 1 part.
2. Place the part flat in the tray, label facing up.
Diversity: Vary part types."""


def _graph(**kw):
    q = lambda t, inf=False: {"quote": t, "inferred": inf}  # noqa: E731
    d = {
        "task_id": "t", "name": "move parts",
        "objects": [{"id": "part", "name": "part", "kinds": ["bolt", "nut"], "source": q("Parts.")},
                    {"id": "tray", "name": "tray", "source": q("To: Tray.")}],
        "nodes": [{"id": "start", "name": "start", "kind": "start"},
                  {"id": "s01_pick", "name": "pick", "description": "Pick up 1 part.", "source": q("Pick up 1 part.")},
                  {"id": "s02_place", "name": "place", "description": "Place the part", "effect_description": "in tray",
                   "source": q("Place the part flat in the tray, label facing up.")},
                  {"id": "end", "name": "end", "kind": "end"}],
        "edges": [{"source": "start", "target": "s01_pick"}, {"source": "s01_pick", "target": "s02_place"},
                  {"source": "s02_place", "target": "end"}],
        "starting_state": [{"description": "parts on the bench", "objects": ["part"], "source": q("From: Bench.")}],
        "repeat_blocks": [{"id": "r1", "steps": ["s01_pick", "s02_place"], "unit": "one part", "objects": ["part"],
                           "until_description": "no part left on the bench", "source": q("Pick up 1 part.")}],
        "acceptance": [{"id": "a1", "step": "s02_place", "objects": ["part"], "criterion": "label facing up",
                        "source": q("label facing up")}],
        "constraints": [{"id": "c1", "rule": "Do not drop parts into the tray.", "applies_to": ["s02_place"],
                         "violation_looks_like": "part released above the tray", "source": q("Do not drop parts into the tray.")}],
        "not_modelled": [{"quote": "Diversity: Vary part types.", "reason": "collection instruction"}],
    }
    d.update(kw)
    return d


def test_v2_validates_and_v1_loader_reads_it(tmp_path):
    g = TaskGraphV2.model_validate(DV.normalize(_graph(), SOP))
    assert g.node_map["s01_pick"].permitted_repeats == UNBOUNDED and g.constraints[0].taxonomy == "violation"
    p = tmp_path / "g.yaml"
    save_graph(g, p)
    v1 = load_graph(p)  # version 1 ignores the added fields
    assert [n.id for n in v1.nodes] == [n.id for n in g.nodes] and not hasattr(v1, "acceptance")
    assert load_graph_v2(p).acceptance[0].criterion == "label facing up"


def test_block_and_references_validated():
    bad = _graph(repeat_blocks=[{"id": "r1", "steps": ["s02_place", "s01_pick"], "unit": "u", "until_description": "x"}])
    with pytest.raises(ValueError):
        TaskGraphV2.model_validate(bad)
    with pytest.raises(ValueError):
        TaskGraphV2.model_validate(_graph(acceptance=[{"id": "a", "step": "s09", "criterion": "x"}]))


def test_normalize_marks_quotes_not_in_sop_inferred():
    d = _graph()
    d["objects"][1]["source"] = {"quote": "a tray made of steel", "inferred": False}
    g = TaskGraphV2.model_validate(DV.normalize(d, SOP))
    assert g.object_map["tray"].source.inferred and not g.object_map["part"].source.inferred


def test_coverage_and_lint():
    assert "Pick up 1 part." in sentences(SOP) and "Steps:" not in sentences(SOP)
    assert quote_in_sop("place the part FLAT in the tray", SOP)
    g = TaskGraphV2.model_validate(DV.normalize(_graph(), SOP))
    codes = {i.code for i in lint_v2(g, SOP)}
    assert not codes & {"E101", "E102"}
    g2 = TaskGraphV2.model_validate(DV.normalize(_graph(not_modelled=[]), SOP))
    assert any(i.code == "W101" and "Diversity" in i.message for i in lint_v2(g2, SOP))
    assert not covered("Vary part types and colours of trays", ["Pick up 1 part."])


def test_v2_prompts_and_schema():
    from procqc import prompts
    assert "repeat_blocks" in prompts.get("graph.v2.build.system")
    assert "never merging two" in prompts.get("graph.v2.build.system")
    s = DV.llm_schema()
    assert "acceptance" in s["required"] and "source" in s["$defs"]["NodeV2"]["required"]
