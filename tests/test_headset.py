"""Headset checks: pure helpers on synthetic inputs and the example Meta_Pilot graph (no data, no model calls)."""
import json
import re
from pathlib import Path

import numpy as np
import pytest

from procqc.internal import manifest
from procqc.internal.fts_ground_truth import _sop_line
from procqc.internal.s3_fetch import _prefix, plan
from procqc.judges import termination_v2 as tv2
from procqc.signals import gesture_verify as gv
from procqc.signals.lighting import frame_stats
from procqc.signals.pickplace import entry_kind, field_kind, held_steps
from procqc.signals.stats import auc
from procqc.signals.trips import held_at
from procqc.signals.tsr import count_floor, required_steps
from procqc.signals.walk_v2 import walks

EX = Path(__file__).resolve().parents[1] / "examples" / "meta_pilot"
TASK = "return_pet_toys_from_floor_to_pet_toy_bin"


def _graph():
    return tv2.load_graph(EX / "graph" / f"{TASK}.yaml")


def _sop():
    return (EX / "sop" / f"{TASK}.txt").read_text()


# ---------------------------------------------------------------- walks and trips

def test_walk_v2_finds_one_slow_walk_and_ignores_sway():
    hz = 72
    t = np.arange(0, 12, 1 / hz)
    x = np.zeros_like(t)
    walk = (t >= 3) & (t < 7)  # 2 m in 4 s = 0.5 m/s
    x[walk] = (t[walk] - 3) * 0.5
    x[t >= 7] = 2.0
    x += 0.02 * np.sin(2 * np.pi * 1.5 * t)  # head sway while standing
    w = walks(t, np.stack([x, np.zeros_like(x)], axis=1))
    assert len(w) == 1
    assert 2.8 <= w[0]["start"] <= 3.5 and 6.5 <= w[0]["end"] <= 7.2
    assert abs(w[0]["displacement_m"] - 2.0) < 0.2


def test_walk_v2_drops_short_shuffles():
    hz = 72
    t = np.arange(0, 6, 1 / hz)
    x = np.clip((t - 2) * 0.3, 0, 0.3)  # 0.3 m step: below the displacement floor
    assert walks(t, np.stack([x, np.zeros_like(x)], axis=1)) == []


def test_held_at_tracks_picks_and_places():
    ev = [{"t": 1, "action": "pick", "object": "a"}, {"t": 2, "action": "pick", "object": "b"},
          {"t": 3, "action": "place", "object": "a"}]
    assert held_at(ev, 0.5) == []
    assert held_at(ev, 2.5) == ["a", "b"]
    assert held_at(ev, 3.5) == ["b"]


# ---------------------------------------------------------------- pick / place from narration

def test_held_steps_on_example_graph():
    picks, places = held_steps(_graph())
    assert picks and places and not picks & places


def test_entry_and_field_kind():
    picks, places = frozenset({"s_pick"}), frozenset({"s_place"})
    assert entry_kind({"matched_step_id": "s_pick"}, picks, places) == "pick"
    assert entry_kind({"matched_step_ids": ["s_place"]}, picks, places) == "place"
    assert entry_kind({"matched_step_ids": ["s_pick", "s_place"]}, picks, places) == "move"
    assert field_kind({"hand": "right", "from_location": "floor", "to_location": "right hand"}) == "pick"
    assert field_kind({"hand": "right", "from_location": "right hand", "to_location": "bin"}) == "place"
    assert field_kind({"hand": "none"}) == "walk"
    # matched to a non-pick/place step, nothing about the object changed, mostly walking -> walk
    assert entry_kind({"matched_step_id": "s_walk", "hand": "right", "state_change": "no change"},
                      picks, places, walk_share=0.9) == "walk"


# ---------------------------------------------------------------- termination v2

def test_goal_conditions_from_sop_and_graph():
    gc = tv2.goal_conditions(_graph(), _sop())
    assert gc["to"] and gc["from"] and gc["count"]
    assert gc["conditions"][0]["id"] == "C1" and gc["conditions"][0]["type"] == "completion"
    assert gc["final_steps"]


def _items(*at_end, identity="clear"):
    return [{"item": f"item {k}", "first_seen": "floor", "last_handled_s": 1.0 + k, "at_end": a,
             "end_place": "somewhere", "identity": identity} for k, a in enumerate(at_end)]


def test_decide_split_rules():
    gc = tv2.goal_conditions(_graph(), _sop())
    met = [{"id": "C1", "answer": "met", "evidence": "", "time_s": 5}]
    not_met = [{"id": "C1", "answer": "not_met", "evidence": "", "time_s": 5}]
    f, _ = tv2.decide_split(gc, {"items": _items("at_destination", "at_destination"), "conditions": met}, 10, True)
    assert f is None
    f, _ = tv2.decide_split(gc, {"items": _items("at_destination", "at_starting_place"), "conditions": not_met}, 10, True)
    assert f["kind"] == "early_termination" and f["status"] == "confirmed"
    f, _ = tv2.decide_split(gc, {"items": _items("at_destination", "elsewhere"), "conditions": met}, 10, True)
    assert f["kind"] == "wrong_destination" and f["status"] == "needs_review"
    f, _ = tv2.decide_split_id(gc, {"items": _items("at_starting_place", identity="uncertain"),
                                    "conditions": not_met}, 10, True)
    assert f["kind"] == "early_termination" and f["status"] == "needs_review"


def test_split_prompts_are_registered_variants():
    assert "end_place" in tv2.SPLIT_SYSTEM and '"identity"' in tv2.SPLIT_ID_SYSTEM
    assert set(tv2.DECIDE) == set(tv2.PROMPTS)


# ---------------------------------------------------------------- gestural anchoring

def test_gesture_templates_format():
    for system, _, _ in gv.VERIFIERS.values():
        s = system.format(which="end", where="end")
        assert "{" in s and "{which}" not in s


def test_score_end():
    rec = {"judgement": {"items": [{"at_end": "at_destination", "last_handled_s": 20.0}], "conditions": []},
           "findings": []}
    ok = gv.score_end({"marker": {"start": 21.0, "end": 22.0}, "status": "pass"}, rec, 23.0)
    assert ok["score"] == "perfect"
    late = gv.score_end({"marker": {"start": 21.0, "end": 22.0}, "status": "pass"}, rec, 30.0)
    assert late["score"] == "medium"  # 8 s of footage after the end signal
    missing = gv.score_end({"marker": None, "status": "confirmed"}, rec, 23.0)
    assert missing["score"] == "discard"
    term = dict(rec, findings=[{"kind": "early_termination", "status": "confirmed"}])
    assert gv.score_end({"marker": {"start": 21.0, "end": 22.0}, "status": "pass"}, term, 23.0)["score"] == "discard"


def test_score_start():
    m = {"marker": {"start": 0.5, "end": 1.5}, "status": "pass"}
    assert gv.score_start(m, [{"kind": "walk", "start": 2.0, "end": 4.0}])["score"] == "perfect"
    assert gv.score_start(m, [{"kind": "walk", "start": 6.0, "end": 8.0}])["score"] == "medium"
    assert gv.score_start(m, [{"kind": "bend", "start": 0.2, "end": 0.4}])["score"] == "needs_review"
    assert gv.score_start({"marker": None, "status": "confirmed"}, [])["score"] == "discard"


# ---------------------------------------------------------------- TSR, lighting, stats

def test_count_floor_and_required_steps():
    g = _graph()
    assert count_floor(g) == 2
    assert required_steps(g) and "start" not in required_steps(g)


def test_frame_stats_dark_and_bright():
    dark = frame_stats(np.full((360, 640, 3), 10, np.uint8))
    bright = frame_stats(np.full((360, 640, 3), 250, np.uint8))
    assert dark["dark_frac"] == 1.0 and bright["clip_frac"] == 1.0 and dark["contrast"] == 0.0


def test_auc():
    assert auc([3, 4], [1, 2]) == 1.0
    assert auc([1], [1]) == 0.5
    assert auc([], [1]) is None


# ---------------------------------------------------------------- internal data helpers

def test_s3_plan_and_prefix(tmp_path):
    assert _prefix("/a/b/clip/original_video.mp4") == "a/b/clip/"
    objs = [{"key": "a/b/clip/original_video.mp4", "size": 10}, {"key": "a/b/clip/hmd.jsonl", "size": 2},
            {"key": "a/b/clip/preview.mp4", "size": 3}, {"key": "a/b/clip/debug.log", "size": 1}]
    jobs = plan(objs, "cid", tmp_path / "v", tmp_path / "s", "original_video.mp4", ["*.log"])
    assert [(k, p) for k, _, p in jobs] == [("a/b/clip/original_video.mp4", tmp_path / "v" / "cid.mp4"),
                                            ("a/b/clip/hmd.jsonl", tmp_path / "s" / "cid" / "hmd.jsonl")]


def test_internal_names_come_from_settings(tmp_path, monkeypatch):
    import procqc.internal as internal
    env = tmp_path / ".env"
    env.write_text("S3_BUCKET=some-bucket\nAUTOQC_TASKS_TABLE=schema_a.table_b\nBAD_TABLE=x; DROP TABLE y\n")
    monkeypatch.setattr(internal, "ENV", env)
    monkeypatch.delenv("FTS_WORKFLOW_ID", raising=False)
    assert internal.setting("S3_BUCKET") == "some-bucket"
    assert internal.sql_name("AUTOQC_TASKS_TABLE") == "schema_a.table_b"
    assert internal.sql_name("FTS_SCHEMA", "public") == "public"
    with pytest.raises(SystemExit):
        internal.sql_name("BAD_TABLE")
    with pytest.raises(SystemExit):
        internal.setting("FTS_WORKFLOW_ID")


def test_no_internal_names_in_code():
    from procqc.internal import fts_ground_truth, s3_fetch
    for mod in (fts_ground_truth, s3_fetch):
        src = Path(mod.__file__).read_text()
        assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", src)
        assert not re.search(r"\b(?:FROM|JOIN)\s+(?!\{)[A-Za-z_]+\.", src)  # every schema comes from settings


def test_sop_line():
    text = "Name: X\n\nFrom: Floor.\nTo:\n\nBin.\n"
    assert _sop_line(text, "From") == "Floor."
    assert _sop_line(text, "To") == "Bin."
    assert _sop_line(text, "Items") == ""


def test_manifest_roundtrip(tmp_path):
    sensors, videos = tmp_path / "sensors", tmp_path / "videos"
    (sensors / "s1").mkdir(parents=True)
    videos.mkdir()
    (videos / "s1.mp4").write_bytes(b"")
    task = {"title": "Return pet toys from floor to pet toy bin", "instructions": _sop().split("Description:\n", 1)[1][:-1]}
    (sensors / "s1" / "session.json").write_text(json.dumps({"task": task, "durationMs": 63920}))
    manifest.write_sops(sensors, tmp_path / "sop")
    assert (tmp_path / "sop" / f"{TASK}.txt").read_text() == _sop()
    ev = tmp_path / "events.jsonl"
    ev.write_text(json.dumps({"session": "s1", "markers": {"end": {"start": 61.97, "end": 63.93}}}) + "\n")
    out = tmp_path / "manifest.jsonl"
    manifest.build(videos, sensors, tmp_path / "sop", EX / "graph", out, str(ev))
    row = json.loads(out.read_text())
    assert row["task_id"] == TASK and row["duration_s"] == 63.92 and row["end_marker"] == {"start": 61.97, "end": 63.93}
