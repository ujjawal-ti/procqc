"""Start / end signal check: the standard sensor event log (v1, procqc.signals.sensors,
unchanged) plus a frame verifier where the log flags.

The Snowbird rubric's start and end signal is two thumbs up in the viewing field (Gestural Anchoring:
recording_start / recording_end). Per marker the sensor log gives:
  two hands          -> pass, no call
  one hand / missing -> flagged; frames from the marker's moment (or the first / last seconds when there is no
                        marker) go to one Fuelix gemini-3.8-flash call that says what the frames show.
On the 100 Meta pilot recordings the sensor log's finger-curl threshold misses loosely closed hands (10 markers
reported one-handed that reviewers scored perfect) and very short gestures at the very start (3 starts missing).

Decision for a flagged marker (code):
  frames show two thumbs up -> pass (the sensor log missed it)
  one thumb up              -> needs_review (the protocol asks for two)
  no thumbs-up              -> confirmed: the signal is missing
  unclear                   -> needs_review

Verifier v2 (--verifier v2): v1 turned a deliberate two-handed signal that was not a clear upright thumbs-up
(arms stretched forward, thumbs angled) into "none" -> confirmed missing, against the reviewers on 2 of 100 starts.
The rubric discards only when the signal is missing or unclear and the boundary cannot be identified, so v2 adds
"other_signal" (the hands are raised in a deliberate signal, but it is not a clear thumbs-up) -> needs_review, and
"none" means no deliberate hand signal at all.

Recording boundaries (--termination RUN_DIR): the rubric's recording_start / recording_end score from the time
between the signal and the task, with no model call (sensor events + the termination check's judgement):
  end    discard       the termination check confirmed the task unfinished at the end signal, or the end signal is
                       confirmed missing (needs_review when either of those is needs_review)
         medium        more than TOL_S between the goal state (latest placement of any task item, wherever it was
                       put, else the time the completion condition was met) and the end signal, more than TOL_S of
                       footage after the end signal, or the end signal held longer than HOLD_MAX_S
                       a goal time later than the end signal by more than GOAL_SLACK_S is invalid (the termination
                       check only sees the recording up to the end signal): no gap is measured and a note is kept
         perfect       otherwise
  start  discard       the start signal is confirmed missing (needs_review when the signal is needs_review);
         needs_review  a bend or grip begins before the start signal (the task may already have started; the
                       sensor grip is unreliable, so not discard on its own)
         medium        more than TOL_S of footage before the start signal, or more than TOL_S between the start
                       signal and the first activity (walk, bend or grip)
         perfect       otherwise
TOL_S = 2 s is the rubric's own pause limit (Natural Transitions: no pause longer than 2 seconds).
HOLD_MAX_S = 3 s: the headset app appears to stop recording about 2 s after it sees the end gesture (end markers last
1.9-2.1 s on 126 of 166 recordings, 2.1-3 s on 18, under 1.9 s on 13, over 3 s on 9), so a longer hold is footage
after the signal; 3 s allows 1 s of slack. The 2 s stop was observed on our recordings, so the limit is not from
the rubric.
GOAL_SLACK_S = 1 s: two frames at the termination check's 2 fps.

Usage (from the repository root):
  python3 -m procqc.signals.gesture_verify EVENTS.jsonl VIDEO_DIR OUT_DIR [--only SESSION ...] [--verifier v1|v2]
      [--gestures gestures.jsonl ...] [--termination RUN_DIR] [--gt ground_truth.csv]
--gestures reuses earlier verifier outputs instead of calling the model (a later file overrides an earlier one per
session), so the boundary score costs nothing.
"""
from __future__ import annotations

import argparse
import contextvars
import csv
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from procqc import pricing, prompts
from procqc.signals.frames import VideoReader, to_jpeg_b64

MODEL = "gemini-3.8-flash"
EFFORT = "low"
N_FRAMES = 6
LONG_EDGE = 768
PAD_S = 0.3
EMPTY_WINDOW_S = {"start": 3.0, "end": 4.0}
TOL_S = 2.0  # rubric, Natural Transitions: no pause longer than 2 seconds
HOLD_MAX_S = 3.0  # app stops ~2 s after the end gesture; longer = footage after the signal
GOAL_SLACK_S = 1.0  # two frames at the termination check's 2 fps
ACTIVITY = ("walk", "bend", "grip")


# Templates: {which} = "start" or "end", {where} = "beginning" or "end".
SYSTEM = prompts.get("gesture.verify.system")
SYSTEM_V2 = prompts.get("gesture.verify_v2.system")

SCHEMA = {"type": "object", "properties": {
    "signal": {"type": "string", "enum": ["two_thumbs_up", "one_thumb_up", "none", "unclear"]},
    "frames": {"type": "array", "items": {"type": "number"}},
    "evidence": {"type": "string"}}, "required": ["signal", "frames", "evidence"]}

DECIDE = {"two_thumbs_up": "pass", "one_thumb_up": "needs_review", "none": "confirmed", "unclear": "needs_review"}

SCHEMA_V2 = json.loads(json.dumps(SCHEMA))
SCHEMA_V2["properties"]["signal"]["enum"].insert(2, "other_signal")
DECIDE_V2 = {**DECIDE, "other_signal": "needs_review"}
VERIFIERS = {"v1": (SYSTEM, SCHEMA, DECIDE), "v2": (SYSTEM_V2, SCHEMA_V2, DECIDE_V2)}


def sensor_status(marker: Optional[dict]) -> str:
    if not marker:
        return "missing"
    return "two_hands" if len(marker.get("hands") or []) >= 2 else "one_hand"


def window(which: str, marker: Optional[dict], duration: float) -> tuple:
    if marker:
        return max(0.0, marker["start"] - PAD_S), min(duration, marker["end"] + PAD_S)
    w = EMPTY_WINDOW_S[which]
    return (0.0, min(duration, w)) if which == "start" else (max(0.0, duration - w), duration)


def verify(video: str, which: str, a: float, b: float, client, version: str = "v1") -> dict:
    times = [round(a + (b - a) * k / (N_FRAMES - 1), 2) for k in range(N_FRAMES)]
    with VideoReader(video) as v:
        frames = v.frames_at(times)
    content: List[dict] = []
    for f, t in zip(frames, times):
        if f is None:
            continue
        content.append({"type": "text", "text": f"frame @ {t:.2f}s:"})
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{to_jpeg_b64(f, LONG_EDGE)}"}})
    content.append({"type": "text", "text": "Return the JSON."})
    system_t, schema, _ = VERIFIERS[version]
    system = system_t.format(which=which, where="beginning" if which == "start" else "end")
    data = client.complete_json_messages([{"role": "system", "content": system}, {"role": "user", "content": content}],
                                         schema=schema, schema_name="gesture", model=MODEL, max_tokens=1500,
                                         reasoning_effort=EFFORT)
    data = data if isinstance(data, dict) else {}
    data["frames_sent_s"] = times
    return data


def check_session(e: dict, video: str, client, version: str = "v1") -> dict:
    out = {"session": e["session"], "duration_s": e["duration_s"]}
    for which in ("start", "end"):
        m = e["markers"].get(which)
        st = sensor_status(m)
        r = {"sensor": st, "marker": m}
        if st == "two_hands":
            r["status"] = "pass"
        else:
            a, b = window(which, m, e["duration_s"])
            with pricing.timed_stage("gesture_verify"):
                v = verify(video, which, a, b, client, version)
            r.update(window_s=[round(a, 2), round(b, 2)], verifier=v,
                     status=VERIFIERS[version][2].get(str(v.get("signal", "unclear")), "needs_review"), verifier_version=version)
        out[which] = r
    return out


def _goal_time(rec: dict) -> Optional[float]:
    j = rec.get("judgement") or {}
    # the last placement of any task item: whether it went to the right place is the destination check's question
    placed = [i["last_handled_s"] for i in j.get("items", [])
              if i.get("at_end") != "at_starting_place" and i.get("last_handled_s") is not None]
    if placed:
        return float(max(placed))
    c1 = next((c for c in j.get("conditions", []) if c.get("id") == "C1" and c.get("answer") == "met"), None)
    return float(c1["time_s"]) if c1 and c1.get("time_s") is not None else None


def _worst(scores: List[str]) -> str:
    order = ["perfect", "medium", "needs_review", "discard"]
    return max(scores, key=order.index)


def score_end(g: dict, rec: Optional[dict], duration: float) -> dict:
    m, sig = g["marker"], g["status"]
    out: Dict = {"signal": sig, "reasons": []}
    scores = ["perfect"]
    if sig == "confirmed":
        scores.append("discard"); out["reasons"].append("end signal missing")
    elif sig == "needs_review":
        scores.append("needs_review"); out["reasons"].append("end signal unclear")
    term = [f for f in (rec or {}).get("findings", []) if f.get("kind") == "early_termination"]
    for f in term:
        scores.append("discard" if f.get("status") == "confirmed" else "needs_review")
        out["reasons"].append(f"task unfinished at the end signal ({f.get('status')})")
    if rec is None:
        scores.append("needs_review"); out["reasons"].append("no termination record")
    if m:
        gt = _goal_time(rec) if rec else None
        out["goal_time_s"] = gt
        if gt is not None and gt > m["start"] + GOAL_SLACK_S:
            out["goal_time_invalid"] = True
            out["notes"] = [f"goal time {gt:.1f} s is after the end signal ({m['start']:.1f} s): not used"]
        elif gt is not None and not term:
            out["gap_goal_to_signal_s"] = round(m["start"] - gt, 2)
            if out["gap_goal_to_signal_s"] > TOL_S:
                scores.append("medium"); out["reasons"].append(f"{out['gap_goal_to_signal_s']:.1f} s from goal state to end signal")
        out["signal_hold_s"] = round(m["end"] - m["start"], 2)
        if out["signal_hold_s"] > HOLD_MAX_S:
            scores.append("medium"); out["reasons"].append(f"end signal held {out['signal_hold_s']:.1f} s")
        out["after_signal_s"] = round(duration - m["end"], 2)
        if out["after_signal_s"] > TOL_S:
            scores.append("medium"); out["reasons"].append(f"{out['after_signal_s']:.1f} s of footage after the end signal")
    out["score"] = _worst(scores)
    return out


def score_start(g: dict, events: List[dict]) -> dict:
    m, sig = g["marker"], g["status"]
    out: Dict = {"signal": sig, "reasons": []}
    scores = ["perfect"]
    if sig == "confirmed":
        scores.append("discard"); out["reasons"].append("start signal missing")
    elif sig == "needs_review":
        scores.append("needs_review"); out["reasons"].append("start signal unclear")
    if m:
        out["before_signal_s"] = round(m["start"], 2)
        if m["start"] > TOL_S:
            scores.append("medium"); out["reasons"].append(f"{m['start']:.1f} s of footage before the start signal")
        early = [e for e in events if e["kind"] in ("bend", "grip") and e["start"] < m["start"]]
        if early:
            scores.append("needs_review")
            out["reasons"].append(f"{early[0]['kind']} at {early[0]['start']:.1f} s, before the start signal")
        nxt = sorted(e["start"] for e in events if e["kind"] in ACTIVITY and e["start"] >= m["start"])
        if nxt:
            out["gap_signal_to_activity_s"] = round(max(0.0, nxt[0] - m["end"]), 2)
            if out["gap_signal_to_activity_s"] > TOL_S:
                scores.append("medium")
                out["reasons"].append(f"{out['gap_signal_to_activity_s']:.1f} s from start signal to first activity")
    out["score"] = _worst(scores)
    return out


def score_boundaries(rows: List[dict], ev: Dict[str, dict], term_dir: Path) -> List[dict]:
    recs = {}
    for p in term_dir.glob("recordings/*.json"):
        r = json.loads(p.read_text())
        recs[r["session"]] = r
    out = []
    for r in rows:
        e = ev[r["session"]]
        out.append({"session": r["session"], "recording_start": score_start(r["start"], e["events"]),
                    "recording_end": score_end(r["end"], recs.get(r["session"]), r["duration_s"])})
    return out


def compare_gt(bounds: List[dict], gt_csv: str) -> None:
    gt = {row["clip_id"]: row for row in csv.DictReader(open(gt_csv))}
    for param in ("recording_start", "recording_end"):
        pairs = [(b[param]["score"], gt[b["session"]].get(f"h_{param}", "")) for b in bounds if b["session"] in gt]
        ours = sorted({o for o, _ in pairs})
        humans = sorted({h for _, h in pairs})
        print(f"{param}: ours x human ({len(pairs)} clips)")
        for o in ours:
            print(f"  {o:12s} " + "  ".join(f"{h or '-'}={sum(1 for a, b in pairs if a == o and b == h)}" for h in humans))


def main(argv: Optional[Sequence[str]] = None) -> int:
    from procqc.llm_client import LLMClient
    ap = argparse.ArgumentParser(prog="procqc.signals.gesture_verify")
    ap.add_argument("events")
    ap.add_argument("video_dir")
    ap.add_argument("out")
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--verifier", choices=sorted(VERIFIERS), default="v1")
    ap.add_argument("--gestures", nargs="*", default=None, help="reuse these verifier outputs; no model calls")
    ap.add_argument("--termination", default=None, help="termination_v2 run dir, for the recording boundary score")
    ap.add_argument("--gt", default=None, help="fts_gt/ground_truth.csv, to compare the boundary scores")
    a = ap.parse_args(argv)
    ev = [json.loads(l) for l in open(a.events) if l.strip()]
    if a.only:
        ev = [e for e in ev if any(e["session"].startswith(s) for s in a.only)]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    meter = pricing.CostMeter()
    if a.gestures:
        prior: Dict[str, dict] = {}
        for path in a.gestures:
            for l in open(path):
                if l.strip():
                    r = json.loads(l)
                    prior[r["session"]] = r
        missing = [e["session"] for e in ev if e["session"] not in prior]
        if missing:
            raise SystemExit(f"--gestures has no row for {len(missing)} sessions, e.g. {missing[0]}")
        rows = [prior[e["session"]] for e in ev]
    else:
        client = LLMClient()
        with pricing.use_meter(meter):
            with ThreadPoolExecutor(max_workers=a.workers) as ex:
                # each task runs in a copy of this context so the cost meter sees calls made in worker threads
                futs = [ex.submit(contextvars.copy_context().run, check_session, e,
                                  str(Path(a.video_dir) / f"{e['session']}.mp4"), client, a.verifier) for e in ev]
                rows = [f.result() for f in futs]
    with open(out / "gestures.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")
    for which in ("start", "end"):
        sensor = {k: sum(r[which]["sensor"] == k for r in rows) for k in ("two_hands", "one_hand", "missing")}
        final = {k: sum(r[which]["status"] == k for r in rows) for k in ("pass", "needs_review", "confirmed")}
        print(f"{which}: sensor {sensor} -> final {final}")
    for r in rows:
        for which in ("start", "end"):
            x = r[which]
            if x["sensor"] != "two_hands":
                v = x.get("verifier", {})
                print(f"  {r['session'][:8]} {which:5s} sensor={x['sensor']:8s} frames={v.get('signal')!s:13s} -> "
                      f"{x['status']:12s} {v.get('evidence', '')[:110]}")
    usd = meter.snapshot()["total"]["usd"]
    print(f"${usd:.4f}")
    summary = {"n": len(rows), "usd": usd}
    if a.termination:
        bounds = score_boundaries(rows, {e["session"]: e for e in ev}, Path(a.termination))
        with open(out / "boundaries.jsonl", "w") as f:
            for b in bounds:
                f.write(json.dumps(b) + "\n")
        for param in ("recording_start", "recording_end"):
            summary[param] = {k: sum(b[param]["score"] == k for b in bounds)
                              for k in ("perfect", "medium", "needs_review", "discard")}
            print(f"{param}: {summary[param]}")
        if a.gt:
            compare_gt(bounds, a.gt)
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
