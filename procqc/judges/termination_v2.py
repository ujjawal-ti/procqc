"""Early termination, version 2 (goal-first): is the task's goal achieved at the moment the demonstrator
declares the task done?

Version 1 (termination.py) asks which step was performed last in the final moments. This version asks
about the goal instead: are all task items where the SOP says they must end up, at the END MOMENT.

End moment: the start of the sensor end marker (the final gesture) when the recording has one, else the
end of the clip. A missing end marker is only a protocol note, never evidence that the task is incomplete.

Goal conditions (built from the SOP text and the drafted graph, the same way for every task):
  C1 completion: every task item that started at the SOP's "From" place is at its "To" place. The item
     count comes from the starting state ("Items: 2-4 ..."), so "all items" applies whether or not the
     graph has a repeat block; a repeat block's end condition is quoted as well.
  C2.. placement: the final action's acceptance criteria (or its expected result). When the graph has a
     repeat block, the final action is the block's last step (a step that only says "repeat" is not an
     action).

One call per recording: the whole clip up to the end marker, as native video (2 frames per second by
default; the end state is static, so short actions need not be resolved). The model lists the items it
can track over the recording with their place at the end moment, and answers met / not_met / not_visible
per condition.

Decision (code, not the model's confidence, which is a self-report):
  C1 not_met and at least one item not at the destination -> early_termination, confirmed
  C1 not_met or an item not at the destination, not both  -> early_termination, needs_review
  C1 not_visible                                           -> early_termination, needs_review
  C1 met and no item left                                  -> no finding
  A placement condition not_met is a note (a parameter deviation, judged elsewhere), not termination.

Items rule "split" (--items-rule split; "merged" above is the default): the pilot showed that "not at the
destination" mixes two errors, items never moved (the task stopped early) and items moved to another
place (a wrong destination). With "split" the model places each item at the end moment as at the
destination, still at the starting place, elsewhere (with the place), or unknown, and the code decides:
  an item still at the starting place -> early_termination (confirmed when C1 is not_met, else review)
  else an item elsewhere              -> wrong_destination, needs_review (not termination)
  else C1 not_met or not_visible      -> early_termination, needs_review
  else                                -> no finding

Items rule "split_id": "split" plus identity per item ("clear" task item or "uncertain": it only resembles one).
A termination is confirmed only when an item left at the starting place is a clear task item; when all of
them are uncertain it goes to review.

Usage (from the repository root):
  python3 -m procqc.judges.termination_v2 run MANIFEST OUT [--only SESSION ...] [--fps 2] [--workers 4]
      [--items-rule merged|split|split_id]
MANIFEST rows: {"session", "task_id", "video", "graph", "sop", "end_marker": {"start", "end"} | null}
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from procqc import pricing, prompts
from procqc.signals.frames import VideoReader

FPS = 2.0
TAIL_S = 0.5  # the clip runs a little past the end marker so the end moment is inside it


# ------------------------------------------------------------------------------------------
# goal conditions
# ------------------------------------------------------------------------------------------
def load_graph(path):
    """A drafted v2 graph keeps its v2 fields (repeat blocks, acceptance, starting state); the plain
    loader would drop them. Version-1 graphs load as before."""
    import yaml
    from procqc.graph.io import load_graph as load_v1
    from procqc.graph.schema_v2 import TaskGraphV2
    p = Path(path)
    data = json.loads(p.read_text()) if p.suffix.lower() == ".json" else yaml.safe_load(p.read_text())
    return TaskGraphV2.model_validate(data) if str(data.get("schema_version")) == "2" else load_v1(p)


def sop_fields(sop: str) -> Dict[str, str]:
    """The SOP's own Objects / From / To / Items lines, verbatim ('' when a field is absent)."""
    out: Dict[str, str] = {}
    lines = [l.strip() for l in sop.splitlines()]
    for i, l in enumerate(lines):
        m = re.match(r"^(Objects|From|To|Items)\s*:\s*(.*)$", l, re.I)
        if not m or m.group(1).title() in out:
            continue
        val = m.group(2).strip()
        if not val:  # value on the next non-empty line
            val = next((x for x in lines[i + 1:] if x), "")
        out[m.group(1).title()] = val
    return out


def _scenario_get(g, key: str) -> str:
    other = getattr(getattr(g, "scenario", None), "other", None) or {}
    for k, v in other.items():
        if k.lower() == key.lower():
            return v
    return ""


def final_actions(g) -> List:
    """The steps whose result is the end state: the last step of the last repeat block when there is
    one, else the mandatory final steps, else the last step in order."""
    from procqc.judges.narration import step_dag as _dag
    steps, _, order = _dag(g)
    blocks = getattr(g, "repeat_blocks", None) or []
    if blocks and blocks[-1].steps and blocks[-1].steps[-1] in steps:
        return [steps[blocks[-1].steps[-1]]]
    term = [steps[s] for s in order if steps[s].mandatory_terminal]
    return term or [steps[s] for s in order[-1:]]


def goal_conditions(g, sop: str) -> dict:
    f = sop_fields(sop)
    objects = f.get("Objects") or "; ".join(o.name for o in g.objects)
    src = f.get("From") or _scenario_get(g, "from")
    dst = f.get("To") or _scenario_get(g, "to") or _scenario_get(g, "destination")
    count = f.get("Items") or "; ".join(s.description for s in getattr(g, "starting_state", []) or [])
    blocks = getattr(g, "repeat_blocks", None) or []
    c1 = (f"Every task item ({objects}) that was at the starting place ({src or 'as staged at the start'}) "
          f"is at the destination ({dst or 'the place the final step puts it'}) at the END MOMENT.")
    if blocks:
        c1 += f" The SOP's end condition: {blocks[-1].until_description.rstrip('. ')}."
    conds = [{"id": "C1", "type": "completion", "text": c1}]
    for n in final_actions(g):
        acc = [a.criterion for a in getattr(g, "acceptance", []) or [] if a.step == n.id]
        for t in acc or [n.effect_description or n.description or n.name]:
            conds.append({"id": f"C{len(conds) + 1}", "type": "placement", "text": t, "step": n.id})
    return {"objects": objects, "from": src, "to": dst, "count": count, "conditions": conds,
            "final_steps": [n.id for n in final_actions(g)]}


def context(g, gc: dict, end_moment: float, marker: bool) -> str:
    L = [f"TASK: {g.name}", f"TASK ITEMS: {gc['objects']}", f"STARTING PLACE: {gc['from'] or '(not stated)'}",
         f"DESTINATION: {gc['to'] or '(not stated)'}", f"ITEMS STAGED (per the procedure): {gc['count'] or '(not stated)'}"]
    if g.goal:
        L.append("GOAL STATE in the task graph: " + "; ".join(str(p) for p in g.goal))
    L.append("")
    L.append("GOAL CONDITIONS:")
    for c in gc["conditions"]:
        L.append(f"  {c['id']} ({c['type']}): {c['text']}")
    L.append("")
    if marker:
        L.append(f"END MOMENT: {end_moment:.1f} s (the demonstrator's end gesture starts here; judge the state at "
                 f"this moment, the gesture is not a task action and nothing after it counts).")
    else:
        L.append(f"END MOMENT: {end_moment:.1f} s (the end of the clip).")
    L.append("The clip starts at 0 s of the recording. Return the JSON.")
    return "\n".join(L)



SYSTEM = prompts.get("termination_v2.merged.system")
SPLIT_SYSTEM = prompts.get("termination_v2.split.system")
SPLIT_ID_SYSTEM = prompts.get("termination_v2.split_id.system")

SCHEMA = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": {"type": "object", "properties": {
            "item": {"type": "string"}, "first_seen": {"type": "string"},
            "last_handled_s": {"type": ["number", "null"]},
            "at_end": {"type": "string", "enum": ["at_destination", "not_at_destination", "unknown"]}},
            "required": ["item", "first_seen", "last_handled_s", "at_end"]}},
        "conditions": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "answer": {"type": "string", "enum": ["met", "not_met", "not_visible"]},
            "evidence": {"type": "string"}, "time_s": {"type": ["number", "null"]}},
            "required": ["id", "answer", "evidence", "time_s"]}},
        "still_working": {"type": "boolean"},
        "end_state": {"type": "string"},
    },
    "required": ["items", "conditions", "still_working", "end_state"],
}



SPLIT_SCHEMA = json.loads(json.dumps(SCHEMA))
_it = SPLIT_SCHEMA["properties"]["items"]["items"]
_it["properties"]["at_end"]["enum"] = ["at_destination", "at_starting_place", "elsewhere", "unknown"]
_it["properties"]["end_place"] = {"type": "string"}
_it["required"].append("end_place")

# Items rule "split_id": "split" plus whether each item is plainly one of the task items. On the 100 internal
# clips the only termination flag was an object that resembled a task item but was not one (a reviewer
# verdict), so an uncertain item left behind goes to review instead of being confirmed.

SPLIT_ID_SCHEMA = json.loads(json.dumps(SPLIT_SCHEMA))
_it = SPLIT_ID_SCHEMA["properties"]["items"]["items"]
_it["properties"]["identity"] = {"type": "string", "enum": ["clear", "uncertain"]}
_it["required"].append("identity")

PROMPTS = {"merged": (SYSTEM, SCHEMA), "split": (SPLIT_SYSTEM, SPLIT_SCHEMA),
           "split_id": (SPLIT_ID_SYSTEM, SPLIT_ID_SCHEMA)}


# ------------------------------------------------------------------------------------------
# decision
# ------------------------------------------------------------------------------------------
def _count_range(text: str):
    m = re.search(r"(\d+)\s*(?:[-–to]+\s*(\d+))?", text or "")
    if not m:
        return None
    lo = int(m.group(1))
    return lo, int(m.group(2) or lo)


def _answers(data: dict) -> tuple:
    conds = data.get("conditions", []) or []
    return ({str(c.get("id")): str(c.get("answer", "not_visible")).lower() for c in conds},
            {str(c.get("id")): c.get("evidence", "") for c in conds})


def _notes(gc: dict, data: dict, marker: bool) -> List[str]:
    ans, ev = _answers(data)
    items = data.get("items", []) or []
    unknown = [i for i in items if i.get("at_end") == "unknown"]
    notes: List[str] = []
    if not marker:
        notes.append("no end gesture in the sensor log: the clip end is used as the end moment "
                     "(a protocol note, not evidence that the task is incomplete)")
    for c in gc["conditions"]:
        if c["type"] == "placement" and ans.get(c["id"]) == "not_met":
            notes.append(f"placement condition {c['id']} not met ({c['text']}): {ev.get(c['id'], '')} "
                         f"- a parameter deviation, not termination")
    rng = _count_range(gc.get("count", ""))
    if rng and items and len(items) < rng[0]:
        notes.append(f"{len(items)} items tracked, fewer than the {rng[0]}-{rng[1]} the procedure stages "
                     f"(setup or tracking, not judged here)")
    if unknown:
        notes.append(f"{len(unknown)} item(s) not seen well enough to place at the end")
    return notes


def _finding(kind: str, status: str, detail: str, end_moment: float) -> dict:
    return {"kind": kind, "status": status, "final_status": status, "step": None, "detail": detail[:600],
            "evidence": [f"{end_moment:.1f}s"], "reasons": ["termination v2: goal conditions at the end moment"]}


def decide(gc: dict, data: dict, end_moment: float, marker: bool) -> tuple:
    """Items rule "merged": (finding or None, notes)."""
    ans, ev = _answers(data)
    items = data.get("items", []) or []
    left = [i for i in items if i.get("at_end") == "not_at_destination"]
    done = [i for i in items if i.get("at_end") == "at_destination"]
    notes = _notes(gc, data, marker)
    c1 = ans.get("C1", "not_visible")
    if c1 == "met" and not left:
        return None, notes
    if c1 == "not_met" and left:
        status, why = "confirmed", "goal not met at the end moment and items are left outside the destination"
    elif c1 == "not_met":
        status, why = "needs_review", "goal judged not met, but no tracked item is outside the destination"
    elif c1 == "met":
        status, why = "needs_review", "goal judged met, but a tracked item is outside the destination"
    else:
        status, why = "needs_review", "the goal state is not visible at the end moment"
    if data.get("still_working"):
        why += "; the person is still handling a task item at the end moment"
    detail = f"{why}. {len(done)} at destination, {len(left)} left" + (
        ": " + "; ".join(f"{i.get('item')} ({i.get('first_seen')})" for i in left) if left else "") + \
        f". C1 evidence: {ev.get('C1', '')}"
    return _finding("early_termination", status, detail, end_moment), notes


def decide_split(gc: dict, data: dict, end_moment: float, marker: bool) -> tuple:
    """Items rule "split": items never moved mean termination, items moved elsewhere a wrong destination."""
    ans, ev = _answers(data)
    items = data.get("items", []) or []
    start = [i for i in items if i.get("at_end") == "at_starting_place"]
    other = [i for i in items if i.get("at_end") == "elsewhere"]
    done = [i for i in items if i.get("at_end") == "at_destination"]
    notes = _notes(gc, data, marker)
    c1 = ans.get("C1", "not_visible")
    working = "; the person is still handling a task item at the end moment" if data.get("still_working") else ""
    tally = f"{len(done)} at destination, {len(start)} at the starting place, {len(other)} elsewhere"

    def listed(xs):
        return "; ".join(f"{i.get('item')} ({i.get('end_place', '')})" for i in xs)

    if start:
        status = "confirmed" if c1 == "not_met" else "needs_review"
        why = ("items are still at the starting place at the end moment" if c1 == "not_met" else
               f"goal judged {c1}, but an item is still at the starting place")
        f = _finding("early_termination", status, f"{why}{working}. {tally}: {listed(start)}. "
                     f"C1 evidence: {ev.get('C1', '')}", end_moment)
        if other:
            notes.append(f"also moved to another place: {listed(other)}")
        return f, notes
    if other:
        return _finding("wrong_destination", "needs_review",
                        f"every item was moved, but not all to the destination{working}. {tally}: {listed(other)}. "
                        f"C1 evidence: {ev.get('C1', '')}", end_moment), notes
    if c1 == "met":
        return None, notes
    why = ("goal judged not met, but every tracked item is at the destination" if c1 == "not_met"
           else "the goal state is not visible at the end moment")
    return _finding("early_termination", "needs_review", f"{why}{working}. {tally}. C1 evidence: {ev.get('C1', '')}",
                    end_moment), notes


def decide_split_id(gc: dict, data: dict, end_moment: float, marker: bool) -> tuple:
    """Items rule "split_id": as "split", but a termination is confirmed only when at least one item left at
    the starting place is plainly a task item; when every such item is uncertain it goes to review."""
    f, notes = decide_split(gc, data, end_moment, marker)
    if f and f["kind"] == "early_termination" and f["status"] == "confirmed":
        start = [i for i in data.get("items", []) or [] if i.get("at_end") == "at_starting_place"]
        if start and all(i.get("identity") == "uncertain" for i in start):
            f["status"] = f["final_status"] = "needs_review"
            f["detail"] = ("the items left at the starting place may not be task items: " + f["detail"])[:600]
    return f, notes


DECIDE = {"merged": decide, "split": decide_split, "split_id": decide_split_id}


# ------------------------------------------------------------------------------------------
# media and run
# ------------------------------------------------------------------------------------------
def cut_clip(video_path: str, end: float, out_dir: Path) -> str:
    """0 s to `end` as a small H.264 clip (cached by source name and end time; atomic rename)."""
    import os
    import uuid
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"{Path(video_path).stem}_0-{end:.1f}.mp4"
    if not dst.exists():
        tmp = dst.with_name(f".{dst.stem}.{uuid.uuid4().hex[:8]}.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video_path, "-t", f"{end:.3f}", "-an",
                        "-vf", "scale=-2:720", "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", str(tmp)],
                       check=True)
        os.replace(tmp, dst)
    return str(dst)


def check_recording(row: dict, gclient, clip_dir: Path, items_rule: str = "merged") -> dict:
    g = load_graph(row["graph"])
    gc = goal_conditions(g, Path(row["sop"]).read_text())
    meter = pricing.CostMeter()
    t0 = time.time()
    with pricing.use_meter(meter):
        with VideoReader(row["video"]) as v:
            duration = v.duration
        m = row.get("end_marker")
        marker = bool(m)
        end_moment = float(m["start"]) if marker else duration
        clip_end = min(duration, end_moment + TAIL_S)
        with pricing.timed_stage("termination_v2_clip"):
            clip = cut_clip(row["video"], clip_end, clip_dir)
        user = context(g, gc, end_moment, marker)
        with pricing.timed_stage("termination_v2_check"):
            system, schema = PROMPTS[items_rule]
            data = gclient.ask(clip, system, user, schema, stage="termination_v2_check")
    data = data if isinstance(data, dict) else {}
    finding, notes = DECIDE[items_rule](gc, data, end_moment, marker)
    snap = meter.snapshot()
    return {"session": row["session"], "task_id": row["task_id"], "duration": duration, "end_moment": end_moment,
            "end_marker": marker, "goal": gc, "judgement": data, "findings": [finding] if finding else [],
            "notes": notes, "clip": clip, "fps": gclient.fps, "items_rule": items_rule,
            "timing_s": {"end_to_end_s": round(time.time() - t0, 2)}, "cost": snap, "usd": snap["total"]["usd"]}


def main(argv: Optional[Sequence[str]] = None) -> int:
    from procqc.video_client import GenAIVideoClient
    ap = argparse.ArgumentParser(prog="procqc.judges.termination_v2")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("manifest")
    r.add_argument("out")
    r.add_argument("--only", nargs="*", default=None, help="session ids to run (default: all rows)")
    r.add_argument("--fps", type=float, default=FPS)
    r.add_argument("--workers", type=int, default=4)
    r.add_argument("--items-rule", choices=sorted(PROMPTS), default="merged")
    a = ap.parse_args(argv)
    rows = [json.loads(l) for l in open(a.manifest) if l.strip()]
    if a.only:
        rows = [x for x in rows if x["session"] in set(a.only)]
    out = Path(a.out)
    (out / "recordings").mkdir(parents=True, exist_ok=True)
    gclient = GenAIVideoClient(fps=a.fps)
    t0 = time.time()

    def one(row):
        p = out / "recordings" / f"{row['session']}.json"
        if p.exists():
            return row["session"], json.loads(p.read_text())
        res = check_recording(row, gclient, out.parent / "_clips_v2", a.items_rule)
        p.write_text(json.dumps(res, indent=1, default=str))
        f = res["findings"][0] if res["findings"] else None
        c1 = next((c.get("answer") for c in res["judgement"].get("conditions", []) if c.get("id") == "C1"), None)
        ends = [i.get("at_end") for i in res["judgement"].get("items", [])]
        left = "/".join(str(ends.count(k)) for k in ("not_at_destination", "at_starting_place", "elsewhere"))
        print(f"{row['session'][:8]} {row['task_id'][:40]:40s} C1={c1!s:11s} items={len(res['judgement'].get('items', []))} "
              f"left/start/else={left} -> {(f['kind'][:5] + ':' + f['status']) if f else '-':18s} {res['timing_s']['end_to_end_s']:.0f}s ${res['usd']:.4f}",
              flush=True)
        return row["session"], res

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        results = dict(ex.map(one, rows))
    summary = {"n": len(results), "elapsed_s": round(time.time() - t0, 1), "fps": a.fps, "items_rule": a.items_rule,
               "usd": round(sum(r["usd"] for r in results.values()), 4),
               "confirmed": sum(any(f["status"] == "confirmed" for f in r["findings"]) for r in results.values()),
               "needs_review": sum(any(f["status"] == "needs_review" for f in r["findings"]) for r in results.values()),
               "by_kind": {k: sum(any(f["kind"] == k for f in r["findings"]) for r in results.values())
                           for k in ("early_termination", "wrong_destination")}}
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
