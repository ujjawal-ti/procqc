"""Pick and place events per task item, from the narration arm's timeline plus the headset sensor events.

First version: the shared narration (procqc.judges.narration) is run on the recording up
to just after the end signal (the clip the early-termination check already cut), and its entries are matched to
the graph's steps (the narration arm's own text pass). An entry's kind comes from the graph first:
  the held state   a predicate on a task object (it has an object argument) that one step sets true and a later
                   step sets false (each graph
                   names it differently: Holding, Grasped, IsHeld, HeldByHandle, ...). The step that sets it true
                   is a pick step, the step that sets it false a place step.
  pick / place     an entry matched to a pick step / a place step (moment: the entry's end: grasp done, release)
  move             an entry matched to both (a pick at its start and a place at its end)
  walk / handle    an entry matched to any other step, or whose state change is "no change" (the narration
                   schema's own marker), is never a pick or place: a walk when it goes from one place to another,
                   has no acting hand, or the sensor walk covers at least WALK_SHARE of it; otherwise handle
Other entries fall back to their own fields:
  walk    no hand acts (hand "none")
  pick    from a place to a hand;  place  from a hand to a place;  move  from a place to another place
  handle  a hand acts with no transfer (adjust, open, smooth)
A location "is a hand" when it names a hand (the schema's hand field is left / right / both).

Each event gets the sensor context at its moment (procqc.signals.sensors event log): walking (a walk
event covers the moment), bending (a bend covers it, within BEND_PAD_S), standing still. And per recording:
  items     per object name: picks, places, the places it went through, where it ended
  walks     each sensor walk with the objects held during it (picked and not yet placed)
These are inputs for the rubric checks (navigation and manipulation, task efficiency, object grouping, object
handling, task-specific requirements); no rule is applied here.

Usage (from the repository root):
  python3 -m procqc.signals.pickplace MANIFEST EVENTS.jsonl TERMINATION_RUN_DIR OUT_DIR [--only ID ...]
      [--fps 5] [--workers 4]
The manifest is the termination manifest (session, task_id, graph, sop, video, end_marker).
"""
from __future__ import annotations

import argparse
import contextvars
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from procqc import pricing

BEND_PAD_S = 0.5
FPS = 5.0
WALK_SHARE = 0.5


def held_steps(g) -> tuple:
    """(pick step ids, place step ids) from the graph's held state: a predicate set true by one step and false by
    a later step, on the same object."""
    order = [n for n in g.nodes if n.is_step]
    sets = {}
    for i, n in enumerate(order):
        for e in getattr(n, "effects", []) or []:
            if not getattr(e, "args", None):  # a state of the person (at the table), not of a task object
                continue
            key = (e.name, tuple(e.args))
            sets.setdefault(key, []).append((i, n.id, bool(e.value)))
    picks, places = set(), set()
    for key, xs in sets.items():
        ons = [x for x in xs if x[2]]
        offs = [x for x in xs if not x[2]]
        if ons and offs and min(i for i, _, _ in ons) < max(i for i, _, _ in offs):
            picks |= {sid for _, sid, _ in ons}
            places |= {sid for _, sid, _ in offs}
    return picks, places


def _covers(events: List[dict], kind: str, t: float, pad: float = 0.0) -> Optional[dict]:
    return next((e for e in events if e["kind"] == kind and e["start"] - pad <= t <= e["end"] + pad), None)


def sensor_context(events: List[dict], t: float) -> dict:
    w, b, s = _covers(events, "walk", t), _covers(events, "bend", t, BEND_PAD_S), _covers(events, "still", t)
    return {"walking": bool(w), "bending": bool(b), "still": bool(s),
            "walk": [w["start"], w["end"]] if w else None, "bend_place": b.get("place") if b else None}


def _is_hand(loc) -> bool:
    return bool(loc) and "hand" in str(loc).lower()


def _overlap(sensor_events: List[dict], kind: str, a: float, b: float) -> float:
    """Share of [a, b] covered by sensor events of this kind."""
    if b <= a:
        return 0.0
    cov = sum(max(0.0, min(b, e["end"]) - max(a, e["start"])) for e in sensor_events if e["kind"] == kind)
    return round(min(1.0, cov / (b - a)), 2)


def entry_kind(a: dict, picks: frozenset = frozenset(), places: frozenset = frozenset(),
               walk_share: float = 0.0) -> str:
    sids = set(a.get("matched_step_ids") or ([a["matched_step_id"]] if a.get("matched_step_id") else []))
    if sids & picks and sids & places:
        return "move"
    if sids & picks:
        return "pick"
    if sids & places:
        return "place"
    k = field_kind(a)
    if sids or _no_change(a):  # matched to a step that is not a pick or place, or nothing about the object changed
        return "walk" if k in ("walk", "move") or walk_share >= WALK_SHARE else "handle"
    return k


def _no_change(a: dict) -> bool:
    """The narration schema's own marker for an entry that changes nothing about its object."""
    return str(a.get("state_change") or "").strip().lower().rstrip(".") in ("no change", "none", "")


def field_kind(a: dict) -> str:
    hand, src, dst = str(a.get("hand") or "").strip().lower(), a.get("from_location"), a.get("to_location")
    if hand in ("", "none", "null", "no hand"):
        return "walk"
    if src and _is_hand(dst) and not _is_hand(src):
        return "pick"
    if dst and _is_hand(src) and not _is_hand(dst):
        return "place"
    if src and dst and not _is_hand(src) and not _is_hand(dst) and src != dst:
        return "move"
    return "handle"


def events_from_narration(narr: dict, sensor_events: List[dict], picks=frozenset(), places=frozenset()) -> List[dict]:
    out = []
    for i, a in enumerate(narr.get("actions", []) or []):
        if a.get("scene_change"):
            continue
        st, en = float(a["start_s"]), float(a["end_s"])
        k = entry_kind(a, picks, places, _overlap(sensor_events, "walk", st, en))
        base = {"entry": i, "kind": k, "object": a.get("object", ""), "hand": a.get("hand", ""),
                "verb": a.get("verb", ""), "start": st, "end": en, "from": a.get("from_location"),
                "to": a.get("to_location"),
                "step_ids": a.get("matched_step_ids") or ([a["matched_step_id"]] if a.get("matched_step_id") else []),
                "walk_share": _overlap(sensor_events, "walk", st, en)}
        if k == "move":
            out.append({**base, "action": "pick", "t": st, "place": base["from"], "sensor": sensor_context(sensor_events, st)})
            out.append({**base, "action": "place", "t": en, "place": base["to"], "sensor": sensor_context(sensor_events, en)})
        elif k in ("pick", "place"):
            loc = base["from"] if k == "pick" else base["to"]
            out.append({**base, "action": k, "t": en, "place": loc, "sensor": sensor_context(sensor_events, en)})
    return sorted(out, key=lambda e: (e["t"], e["action"] == "pick"))


def narrated_walks(narr: dict, sensor_events: List[dict], picks=frozenset(), places=frozenset()) -> List[dict]:
    out = []
    for i, a in enumerate(narr.get("actions", []) or []):
        st, en = float(a["start_s"]), float(a["end_s"])
        share = _overlap(sensor_events, "walk", st, en)
        if entry_kind(a, picks, places, share) == "walk":
            out.append({"entry": i, "start": st, "end": en, "from": a.get("from_location"), "to": a.get("to_location"),
                        "sensor_walk_share": share})
    return out


def item_log(events: List[dict]) -> Dict[str, dict]:
    items: Dict[str, dict] = {}
    for e in events:
        it = items.setdefault(e["object"], {"picks": 0, "places": 0, "route": [], "end_place": None})
        it["picks" if e["action"] == "pick" else "places"] += 1
        if not it["route"] or it["route"][-1] != e["place"]:
            it["route"].append(e["place"])
        if e["action"] == "place":
            it["end_place"] = e["place"]
    return items


def walk_log(events: List[dict], sensor_events: List[dict]) -> List[dict]:
    """Each sensor walk with the objects held during it (picked before its middle and not yet placed)."""
    out = []
    for w in (e for e in sensor_events if e["kind"] == "walk"):
        mid = (w["start"] + w["end"]) / 2
        held: Dict[str, int] = {}
        for e in events:
            if e["t"] <= mid:
                held[e["object"]] = held.get(e["object"], 0) + (1 if e["action"] == "pick" else -1)
        out.append({"start": w["start"], "end": w["end"], "distance_m": w.get("distance_m"),
                    "holding": sorted(o for o, n in held.items() if n > 0)})
    return out


def check_recording(row: dict, sensors: dict, clip: str, gclient, text_client) -> dict:
    from procqc import prompts
    from procqc.judges.narration import (NARRATE_SCHEMA, match_narration, narrate_prompt, narrator_context,
                                         normalize_narration_times)
    NARRATE_SYSTEM = prompts.get("narration.narrate.system")
    from procqc.judges.termination_v2 import load_graph
    from procqc.signals.frames import VideoReader
    g = load_graph(row["graph"])
    meter = pricing.CostMeter()
    t0 = time.time()
    with pricing.use_meter(meter):
        with VideoReader(clip) as v:
            duration = v.duration
        with pricing.timed_stage("pickplace_narrate"):
            narr = gclient.ask(clip, NARRATE_SYSTEM, narrate_prompt(narrator_context(g), duration), NARRATE_SCHEMA,
                               stage="pickplace_narrate")
        narr = normalize_narration_times(json.loads(json.dumps(narr if isinstance(narr, dict) else {})), duration)
        with pricing.timed_stage("pickplace_match"):
            match_narration(g, narr, text_client)
    snap = meter.snapshot()
    res = {"session": row["session"], "task_id": row["task_id"], "graph": row["graph"], "clip": clip, "clip_s": duration,
           "end_marker": row.get("end_marker"), "narration": narr, "fps": gclient.fps,
           "timing_s": {"end_to_end_s": round(time.time() - t0, 2)}, "usd": snap["total"]["usd"], "cost": snap}
    return derive(res, sensors)


def derive(res: dict, sensors: dict, graph_path: Optional[str] = None) -> dict:
    """Events, item log and walk logs from a stored narration (no model call; rerun after a rule change)."""
    from procqc.judges.termination_v2 import load_graph
    gp = graph_path or res.get("graph")
    picks, places = held_steps(load_graph(gp)) if gp else (set(), set())
    picks, places = frozenset(picks), frozenset(places)
    sev = sensors.get("events", [])
    ev = events_from_narration(res["narration"], sev, picks, places)
    res.update(graph=gp, pick_steps=sorted(picks), place_steps=sorted(places), events=ev, items=item_log(ev),
               walks=walk_log(ev, sev), narrated_walks=narrated_walks(res["narration"], sev, picks, places))
    return res


def main(argv: Optional[Sequence[str]] = None) -> int:
    from procqc.video_client import GenAIVideoClient
    from procqc.llm_client import LLMClient
    ap = argparse.ArgumentParser(prog="procqc.signals.pickplace")
    ap.add_argument("manifest")
    ap.add_argument("events")
    ap.add_argument("termination")
    ap.add_argument("out")
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--fps", type=float, default=FPS)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--from", dest="from_dir", default=None,
                    help="earlier pickplace output: re-derive its stored narrations into OUT (e.g. with walk v2 "
                         "events) without a model call")
    a = ap.parse_args(argv)
    rows = [json.loads(l) for l in open(a.manifest) if l.strip()]
    if a.only:
        rows = [r for r in rows if any(r["session"].startswith(s) for s in a.only)]
    sensors = {json.loads(l)["session"]: json.loads(l) for l in open(a.events) if l.strip()}
    clips = {}
    for p in Path(a.termination).glob("recordings/*.json"):
        r = json.loads(p.read_text())
        clips[r["session"]] = r["clip"]
    out = Path(a.out)
    (out / "recordings").mkdir(parents=True, exist_ok=True)
    # --from makes no model call, so it needs no credentials
    gclient, tclient = (None, None) if a.from_dir else (GenAIVideoClient(fps=a.fps), LLMClient())

    def one(row):
        p = out / "recordings" / f"{row['session']}.json"
        src = Path(a.from_dir) / "recordings" / p.name if a.from_dir else p
        if a.from_dir and not src.exists():
            return None
        if src.exists():
            res = derive(json.loads(src.read_text()), sensors.get(row["session"], {}), row["graph"])
        else:
            res = check_recording(row, sensors.get(row["session"], {}), clips[row["session"]], gclient, tclient)
        p.write_text(json.dumps(res, indent=1, default=str))
        n_pick = sum(e["action"] == "pick" for e in res["events"])
        n_place = sum(e["action"] == "place" for e in res["events"])
        walking = sum(e["sensor"]["walking"] for e in res["events"])
        print(f"{row['session'][:8]} {row['task_id'][:40]:40s} entries={len(res['narration'].get('actions', []))} "
              f"walks={len(res['narrated_walks'])} picks={n_pick} places={n_place} at_walk={walking} "
              f"items={len(res['items'])} ${res['usd']:.4f}", flush=True)
        return res

    rows = [r for r in rows if r["session"] in clips]
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        res = [f.result() for f in [ex.submit(contextvars.copy_context().run, one, r) for r in rows]]
    res = [r for r in res if r is not None]
    summary = {"n": len(res), "fps": a.fps, "usd": round(sum(r["usd"] for r in res), 4),
               "picks": sum(e["action"] == "pick" for r in res for e in r["events"]),
               "places": sum(e["action"] == "place" for r in res for e in r["events"])}
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
