"""Sensor event log on a synthetic 20 s session (no video, no model calls)."""
import json

import numpy as np

from procqc.signals import sensors as S

HZ = 72
T0 = 1_000_000_000


def _hand(palm, curled=False, thumb_up=False, grip=False):
    """26 joints (OpenXR order) for a schematic hand: hand size (wrist -> middle knuckle) = 0.09 m."""
    p = np.asarray(palm, float)
    j = np.tile(p, (26, 1))
    j[S.WRIST] = p + [0, 0, 0.05]
    j[S.MID_PROX] = p + [0, 0, -0.04]
    j[S.THUMB_META] = p + [0.03, 0, 0]
    j[S.THUMB_TIP] = p + ([0.03, 0.095, 0] if thumb_up else [0.06, 0, -0.06])
    tip = [0, -0.02, -0.03] if curled else ([0, -0.03, -0.08] if grip else [0, 0, -0.12])
    for k in S.TIPS[1:]:
        j[k] = p + tip
    return [list(x) + [0, 0, 0, 1] for x in j]


def _session(tmp_path, lost_left=None):
    n = 20 * HZ
    t = np.arange(n) / HZ
    head, left, right = [], [], []
    for x in t:
        hx = 0.0
        if 3 <= x < 6:
            hx = (x - 3) * 0.6          # walk 1.8 m
        elif x >= 6:
            hx = 1.8
        hy = 1.6
        bend = [(8, 10), (13, 15), (16, 17.5)]
        for a, b in bend:
            if a <= x < b:
                hy = 1.6 - 0.6 * np.sin(np.pi * (x - a) / (b - a))
        spot = 1.8 if x < 15.5 else 4.0      # the third bend is somewhere else
        if 13 <= x < 15:
            spot = 1.8
        tu = x < 1.5 or x >= 18.5
        low = any(a <= x < b for a, b in bend)
        r_palm = [spot if low else hx + 0.2, hy - 1.9 - (0.4 if low else 0), 0.3]
        l_palm = [hx - 0.2, hy - 1.9, 0.3]
        head.append({"t": int(T0 + x * 1e9), "pos": [hx, hy, 0.0], "rot": [0, 0, 0, 1]})
        right.append({"t": int(T0 + x * 1e9), "state": "tracked",
                      "joints": _hand(r_palm, curled=tu, thumb_up=tu, grip=8.5 <= x < 12)})
        state = "lost" if lost_left and lost_left[0] <= x < lost_left[1] else "tracked"
        left.append({"t": int(T0 + x * 1e9), "state": state, "joints": _hand(l_palm, curled=tu, thumb_up=tu)})
    d = tmp_path / "sess"
    d.mkdir()
    (d / "session.json").write_text(json.dumps({"startNs": T0, "durationMs": 20000,
                                                "task": {"title": "Move toys", "description": "Steps: ..."}}))
    for name, rows in (("hmd", head), ("hand-left", left), ("hand-right", right)):
        (d / f"{name}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return d


def _kind(log, k):
    return [e for e in log["events"] if e["kind"] == k]


def test_markers_bends_places_walk(tmp_path):
    log = S.event_log(S.load_session(_session(tmp_path)))
    assert log["markers"]["start"]["hands"] == ["left", "right"] and log["markers"]["start"]["start"] < 0.5
    assert log["markers"]["end"]["end"] > 19.5
    assert not [g for g in _kind(log, "gesture") if g["role"] == "between"]
    bends = _kind(log, "bend")
    assert [round(b["bottom"]) for b in bends] == [9, 14, 17]
    assert all(b["hand"] == "right" for b in bends)
    assert bends[0]["place"] == bends[1]["place"] != bends[2]["place"]
    top = max(log["places"], key=lambda q: q["visits"])
    assert top["visits"] == 2
    walks = _kind(log, "walk")
    assert len(walks) == 1 and abs(walks[0]["distance_m"] - 1.8) < 0.3
    assert abs(log["sample_hz"] - HZ) < 1


def test_grip_is_a_low_reliability_candidate_and_gestures_are_not_grips(tmp_path):
    log = S.event_log(S.load_session(_session(tmp_path)))
    grips = _kind(log, "grip")
    assert [g["hand"] for g in grips] == ["right"]
    assert 8.3 < grips[0]["start"] < 8.8 and 11.7 < grips[0]["end"] < 12.2
    assert grips[0]["reliability"] == "low"


def test_lost_hand_is_reported_and_does_not_break(tmp_path):
    log = S.event_log(S.load_session(_session(tmp_path, lost_left=(5.0, 7.0))))
    lost = log["tracking"]["left"]["lost"]
    assert len(lost) == 1 and abs(lost[0][0] - 5.0) < 0.05 and abs(lost[0][1] - 7.0) < 0.05
    assert log["tracking"]["right"]["lost"] == []
    assert log["tracking"]["left"]["tracked_fraction"] < 0.95


def test_still_before_bend_depends_on_the_threshold(tmp_path):
    d = _session(tmp_path)
    strict = S.event_log(S.load_session(d), S.SensorSettings(still_speed=0.01))
    loose = S.event_log(S.load_session(d))
    assert _kind(strict, "bend")[0]["still_before_s"] <= _kind(loose, "bend")[0]["still_before_s"]
    assert _kind(loose, "bend")[0]["still_before_s"] >= 1.0   # standing from 6 s, bend at 8 s


def test_cli_batch(tmp_path, capsys):
    _session(tmp_path)
    out = tmp_path / "events.jsonl"
    assert S.main([str(tmp_path), "--out", str(out)]) == 0
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["session"] == "sess" and rows[0]["counts"]["bend"] == 3
    assert "1 sessions" in capsys.readouterr().out
