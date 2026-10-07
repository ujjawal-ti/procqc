"""Scorecard metrics and per-kind matching rules (no model calls)."""
from procqc import evaluate as E


def _res(check, flags=(), review=()):
    return {"checks": {check: {"flags": list(flags), "review": list(review), "candidates": list(flags) + list(review)}}}


def test_step_matching_and_recording_counts():
    labels = {"a": {"findings": [{"kind": "omission", "step": "s2"}]}}
    results = {"a": _res("omission", [{"step": "s2"}, {"step": "s5"}]), "b": _res("omission", review=[{"step": "s1"}]),
               "c": _res("omission")}
    e = E.evaluate("omission", results, labels, with_review=False)
    assert e["event"]["tp"] == 1 and e["event"]["fp"] == 1 and e["event"]["fn"] == 0
    assert (e["recording"]["tp"], e["recording"]["fp"], e["recording"]["tn"]) == (1, 0, 2)
    e = E.evaluate("omission", results, labels, with_review=True)
    assert e["recording"]["fp"] == 1 and e["recording"]["false_alarm_rate"] == 0.5


def test_time_overlap_and_repeat_routing():
    labels = {"a": {"findings": [{"kind": "addition_offgraph", "start": 10.0, "end": 13.0},
                                 {"kind": "repeated_addition", "step": "s1", "start": 20, "end": 25}]}}
    results = {"a": {"checks": {
        "offgraph": {"flags": [{"span_s": [12.5, 14.0]}, {"span_s": [40.0, 42.0]}], "review": []},
        "repeat": {"flags": [{"step": "s1", "span_s": [20, 25], "report_as": "parameter_deviation"}], "review": []}}}}
    e = E.evaluate("addition_offgraph", results, labels, False)
    assert (e["event"]["tp"], e["event"]["fp"]) == (1, 1)
    assert E.evaluate("repeated_addition", results, labels, False)["event"]["tp"] == 1
    assert E.evaluate("addition_repeat", results, labels, False)["event"]["tp"] == 0


def test_wrong_tool_covers_later_steps_and_errors_are_skipped():
    labels = {"a": {"findings": [{"kind": "wrong_tool_object", "step": "s1"}, {"kind": "wrong_tool_object", "step": "s4"}]}}
    results = {"a": _res("wrongtool", [{"step": "s1", "also_steps": ["s4"]}]), "b": {"checks": {"wrongtool": {"error": "x"}}}}
    e = E.evaluate("wrong_tool_object", results, labels, False)
    assert e["event"]["tp"] == 2 and e["event"]["fn"] == 0 and e["skipped"] == 1


def test_termination_one_event_per_recording():
    labels = {"a": {"findings": [{"kind": "early_termination"}]}}
    results = {"a": _res("termination", [{"step": "z"}]), "b": _res("termination", review=[{"step": "z"}])}
    card = E.scorecard(results, labels, ["early_termination"])["early_termination"]
    assert card["flags"]["recording"]["tp"] == 1 and card["flags + review"]["recording"]["fp"] == 1
    assert "early_termination" in E.format_scorecard({"early_termination": card})
