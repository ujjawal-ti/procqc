"""Deterministic parts of the per-kind checks: candidates, decisions, windows, routing (no model calls)."""
from procqc.graph.schema import Edge, Node, NodeKind, TaskGraph
from procqc.judges import base, misordering as M, offgraph as OG, omission as O, repeat as R, termination as T
from procqc.judges.base import CONFIRMED, REJECTED, REVIEW


def _chain(ids, terminal=None, repeats=None):
    repeats = repeats or {}
    nodes = [Node(id="start", name="Start", kind=NodeKind.START)] + \
            [Node(id=i, name=i, description=i, mandatory_terminal=(i == terminal), permitted_repeats=repeats.get(i, 1))
             for i in ids] + [Node(id="end", name="End", kind=NodeKind.END)]
    ch = ["start"] + ids + ["end"]
    return TaskGraph(task_id="t", name="t", nodes=nodes, edges=[Edge(source=a, target=b) for a, b in zip(ch, ch[1:])])


def _seq(order, step=10.0):
    return [(i, s, step * i, step * i + 5, 0.9) for i, s in enumerate(order)]


# ----- routing ---------------------------------------------------------------------------
def test_route_sends_rejections_to_review_only_for_router_kinds():
    cands = lambda: [{"status": CONFIRMED}, {"status": REVIEW}, {"status": REJECTED}]  # noqa: E731
    r = base.route("omission", cands())
    assert len(r["flags"]) == 1 and len(r["review"]) == 2 and "routed" in r["review"][1]
    r = base.route("misordering", cands())
    assert len(r["review"]) == 2
    r = base.route("addition_offgraph", cands())
    assert len(r["flags"]) == 1 and len(r["review"]) == 1


def test_confidence_of_defaults():
    assert base.confidence_of({}) == 0.5 and base.confidence_of({"confidence": "x"}) == 0.5
    assert base.confidence_of({"confidence": 0.8}) == 0.8


# ----- omission --------------------------------------------------------------------------
def test_skipped_step_with_dependent_done_is_candidate():
    g = _chain(["a", "b", "c", "d"], terminal="d")
    out = O.find_omissions(g, _seq(["a", "c", "d"]))
    assert [f["step"] for f in out] == ["b"]
    assert out[0]["dependent"] == "c" and out[0]["gap_s"] == [5.0, 10.0] and out[0]["span_s"] == [5.0, 10.0]


def test_unfinished_tail_and_missing_final_step_are_termination_not_omission():
    g = _chain(["a", "b", "c"], terminal="c")
    assert O.find_omissions(g, _seq(["a"])) == []
    assert O.find_omissions(g, _seq(["a", "b"])) == []


def test_omission_decision():
    ok = {"performed_in_gap": "no", "result_before_dependent": "no", "present_at_start": "no", "verdict": "omitted",
          "confidence": 0.9}
    assert O.decide({}, ok) == CONFIRMED
    assert O.decide({}, dict(ok, performed_in_gap="yes")) == REJECTED
    f = {}
    assert O.decide(f, dict(ok, result_before_dependent="yes")) == REJECTED and f["note"] == "offcamera_or_presatisfied"
    assert O.decide({}, dict(ok, result_before_dependent="unclear", verdict="unclear")) == REVIEW
    assert O.decide({}, dict(ok, confidence=0.4)) == REVIEW


def test_omission_clip_windows():
    f = {"gap_s": [5.0, 400.0], "dependent_s": [400.0, 410.0]}
    gap, dep, start = O.clip_windows(f, 1000.0)
    assert gap[1] - gap[0] <= O.GAP_MAX + 3.0 + 1e-9 and dep == [397.0, 415.0] and start == [0.0, O.START_CLIP]


# ----- misordering -----------------------------------------------------------------------
def test_swapped_pair_gives_one_finding_on_the_moved_step():
    g = _chain(["a", "b", "c", "d"])
    out = M.find_misorderings(g, _seq(["a", "c", "b", "d"], 1.0))
    assert [(f["step"], f["prerequisite"]) for f in out] == [("c", "b")]


def test_never_performed_prerequisite_is_not_misordering():
    assert M.find_misorderings(_chain(["a", "b", "c"]), _seq(["a", "c"], 1.0)) == []


def test_consequences_of_one_late_step_are_not_new_findings():
    out = M.find_misorderings(_chain(["a", "b", "c", "d"]), _seq(["a", "c", "d", "b"], 1.0))
    assert [f["step"] for f in out] == ["c"]


def test_multi_step_entries_count_in_order():
    from procqc.judges.narration import performed_sequence
    g = _chain(["pick", "place"])
    narr = {"actions": [{"matched_step_ids": ["pick", "place"], "start_s": 0, "end_s": 2, "confidence": 0.9}]}
    assert M.find_misorderings(g, performed_sequence(g, narr)) == []


def test_misordering_decision_by_state():
    ok = {"s_performed": "yes", "r_result_during_s": "no", "r_result_later": "yes", "verdict": "misordered", "confidence": 0.9}
    assert M.decide({}, ok) == CONFIRMED
    assert M.decide({}, dict(ok, s_performed="no")) == REJECTED
    assert M.decide({}, dict(ok, r_result_during_s="yes")) == REJECTED
    assert M.decide({}, dict(ok, r_result_later="unclear", verdict="unclear")) == REVIEW


def test_misordering_windows_padded_by_typical_duration():
    g = _chain(["a", "b"])
    g.node_map["a"].expected_duration_s = (20.0, 40.0)
    f = {"step": "a", "prerequisite": "b", "start_s": 100.0, "end_s": 102.0,
         "prerequisite_start_s": 300.0, "prerequisite_end_s": 300.0}
    (s0, s1), (r0, r1) = M.windows(g, f, 1000.0)
    assert (s0, s1) == (80.0, 122.0) and (r0, r1) == (295.0, 306.0)


def test_oracle_uses_reference_segments():
    g = _chain(["a", "b"])
    out = M.oracle(g, [{"start": 5, "end": 6, "label": "a"}, {"start": 0, "end": 1, "label": "b"}])
    assert out == [] or out[0]["step"] in {"a", "b"}
    out = M.oracle(_chain(["a", "b", "c"]), [{"start": 0, "end": 1, "label": "a"}, {"start": 2, "end": 3, "label": "c"},
                                            {"start": 4, "end": 5, "label": "b"}])
    assert [f["step"] for f in out] == ["c"]


# ----- off-graph addition ----------------------------------------------------------------
def _onarr(entries):
    """entries: (start, end, matched step or None, scene_change)"""
    return {"actions": [{"start_s": s, "end_s": e, "verb": "v", "object": f"o{i}", "state_change": "x",
                         "matched_step_ids": [m] if m else [], "matched_step_id": m, "scene_change": sc}
                        for i, (s, e, m, sc) in enumerate(entries)]}


def test_unmatched_entries_exclude_matched_and_scene_change():
    assert OG.unmatched(_onarr([(0, 2, "a", False), (2, 4, None, False), (4, 6, None, True)])) == [1]


def test_offgraph_candidates_merge_when_consecutive():
    n = _onarr([(0, 2, "a", False), (2, 4, None, False), (4.5, 6, None, True), (20, 22, None, False),
                (30, 31, None, False)])
    roles = {1: {"role": "unrelated", "reason": "r1"}, 3: {"role": "prepare", "reason": "r3"},
             4: {"role": "unrelated", "reason": "r4"}}
    out = OG.find_additions(n, roles)
    assert [c["entries"] for c in out] == [[1, 2], [4]]
    assert out[0]["sources"] == ["unrelated", "scene_change"] and out[0]["span_s"] == [2.0, 6.0]


def test_supporting_roles_are_not_candidates():
    n = _onarr([(0, 2, None, False), (2, 4, None, False)])
    assert OG.find_additions(n, {0: {"role": "prepare"}, 1: {"role": "tidy"}}) == []


def test_offgraph_clip_windows():
    w = OG.clip_windows({"span_s": [50.0, 51.0]}, 100.0)
    assert w[0][1] - w[0][0] >= OG.MIN_CLIP and w[1] == [w[0][0] - 1.0 - OG.REF_LEN, w[0][0] - 1.0]
    w = OG.clip_windows({"span_s": [1.0, 3.0]}, 100.0)
    assert w[1][0] > w[0][1]  # at the start: reference after the candidate
    w = OG.clip_windows({"span_s": [10.0, 200.0]}, 300.0)
    assert w[0][1] - w[0][0] <= OG.MAX_CLIP


def test_offgraph_decision():
    ok = {"same_setting": "yes", "serves_procedure": "no", "verdict": "addition", "confidence": 0.9}
    assert OG.decide({}, ok) == CONFIRMED
    assert OG.decide({}, dict(ok, serves_procedure="unclear", same_setting="no")) == CONFIRMED
    assert OG.decide({}, dict(ok, serves_procedure="yes", verdict="not_addition")) == REJECTED
    assert OG.decide({}, dict(ok, verdict="unclear", serves_procedure="unclear")) == REVIEW
    assert OG.decide({}, dict(ok, confidence=0.4)) == REVIEW


# ----- repeat ----------------------------------------------------------------------------
def _rnarr(entries):
    """entries: (step or None, continues_entry or None)"""
    return {"actions": [{"start_s": 10.0 * i, "end_s": 10.0 * i + 5, "matched_step_ids": [s] if s else [],
                         "matched_step_id": s, "continues_entry": c} for i, (s, c) in enumerate(entries)]}


def test_second_performance_of_a_once_step_is_candidate():
    g = _chain(["a", "b", "c"])
    perf = R.performances(_rnarr([("a", None), ("b", None), ("b", None), ("c", None)]), {"a", "b", "c"})
    out = R.find_repeats(g, perf)
    assert [(f["step"], f["entry"], f["previous_entry"], f["adjacent"]) for f in out] == [("b", 2, 1, True)]


def test_permitted_repeats_and_continuations_are_not_candidates():
    g = _chain(["a", "b"], repeats={"a": 2})
    assert R.find_repeats(g, R.performances(_rnarr([("a", None), ("b", None), ("a", None)]), {"a", "b"})) == []
    perf = R.performances(_rnarr([("a", None), ("b", None), ("b", 1)]), {"a", "b"})
    assert len(perf) == 2 and perf[1][3] == 25.0
    assert R.find_repeats(_chain(["a", "b"]), perf) == []


def test_third_performance_beyond_two_allowed():
    g = _chain(["a"], repeats={"a": 2})
    out = R.find_repeats(g, R.performances(_rnarr([("a", None), (None, None), ("a", None), ("a", None)]), {"a"}))
    assert [(f["entry"], f["occurrence"]) for f in out] == [(3, 3)]


def test_repeat_decision():
    ok = {"same_step_again": "yes", "first_result_achieved": "yes", "went_wrong": "no", "object_changed": "no",
          "verdict": "redundant_repeat", "confidence": 0.9}
    assert R.decide({}, ok) == CONFIRMED
    f = {}
    assert R.decide(f, dict(ok, verdict="correction", went_wrong="yes")) == REJECTED and f["note"] == "correction"
    assert R.decide({}, dict(ok, verdict="needed_redo")) == REJECTED
    assert R.decide({}, dict(ok, same_step_again="no", verdict="unclear")) == REJECTED
    assert R.decide({}, dict(ok, first_result_achieved="unclear")) == REVIEW


def test_amount_steps_route_to_parameter_deviation():
    texts = {"n1": "Add 1 unit of the material", "n2": "Fit 4 large parts", "n3": "Insert two pins",
             "n4": "Add 1/2 measure of it", "n5": "Hold the button for 30 seconds", "n6": "Wait 5 min",
             "n7": "Close the cover", "n8": "Run step 2 again", "n9": "Repeat 3 times", "n10": "Redo steps 3 to 5"}
    g = TaskGraph(task_id="t", name="t", nodes=[Node(id="start", name="Start", kind=NodeKind.START)]
                  + [Node(id=k, name=k, description=v) for k, v in texts.items()]
                  + [Node(id="end", name="End", kind=NodeKind.END)], edges=[])
    routed = {k: R.route(g, {"step": k})["report_as"] for k in texts}
    assert {k for k, v in routed.items() if v == "parameter_deviation"} == {"n1", "n2", "n3", "n4"}
    assert R.route(g, {"step": "n1"})["tag"] == "repeated_addition"


# ----- termination -----------------------------------------------------------------------
def _tg():
    nodes = [Node(id="start", name="Start", kind=NodeKind.START), Node(id="a", name="Open", description="Open"),
             Node(id="z", name="Close", description="Close", mandatory_terminal=True),
             Node(id="end", name="End", kind=NodeKind.END)]
    edges = [Edge(source="start", target="a"), Edge(source="a", target="z"), Edge(source="z", target="end")]
    return TaskGraph(task_id="t", name="t", nodes=nodes, edges=edges)


def test_termination_decided_by_final_step_result():
    g = _tg()
    assert T.decide(g, {"final_step_result": "present", "confidence": 0.9}, 30.0) is None
    f = T.decide(g, {"final_step_result": "absent", "confidence": 0.9}, 30.0)
    assert f["kind"] == "early_termination" and f["status"] == CONFIRMED and f["step"] == "z"
    assert T.decide(g, {"final_step_result": "absent", "confidence": 0.4}, 30.0)["status"] == REVIEW
    assert T.decide(g, {"final_step_result": "unclear", "confidence": 0.9}, 30.0)["status"] == REVIEW


def test_termination_uses_last_step_sequence():
    g = _tg()
    assert T.decide(g, {"last_position": 2, "final_step_result": "unclear", "confidence": 0.8}, 30.0) is None
    assert T.decide(g, {"last_position": 1, "final_step_result": "present", "confidence": 0.8}, 30.0)["status"] == REVIEW
    assert T.decide(g, {"last_position": 1, "final_step_result": "absent", "confidence": 0.8}, 30.0)["status"] == CONFIRMED


def test_end_window_bounds():
    assert T.end_window(50.0) == (30.0, 50.0)
    assert T.end_window(1000.0) == (940.0, 1000.0)


def test_repeated_steps_get_positions():
    g = _tg()
    g.metadata["canonical_sequence"] = ["a", "z", "a", "z"]
    seq = T.required_sequence(g)
    assert seq == ["a", "z", "a", "z"] and T.final_position(g, seq) == 4
    assert "(2nd time)" in T.final_step_context(g)
    assert T.decide(g, {"last_position": 3, "final_step_result": "present", "confidence": 0.9}, 30.0) is not None
