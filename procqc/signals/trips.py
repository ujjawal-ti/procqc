"""Trip log: task efficiency and object grouping from walks (walk v2) and pick/place events.

The Snowbird rubric:
  task_efficiency  "efficient, avoids unnecessary trips, and picks up objects in their path before walking
                   through"; medium = minor unnecessary trip; discard = highly inefficient or repeated trips.
  object_grouping  "naturally grouped items are moved together ... medium/large objects one at a time ... small
                   items may be grabbed together"; discard = repeatedly handles individually when grouping is
                   natural, or groups unsafely.

A trip is one v2 walk, labelled with what the hands carry at its midpoint (picked and not yet placed). A place of
an object the hands do not hold under that name (a group name such as "pair of slides") puts down everything held.

Signals per recording (no thresholds yet; with --gt the CLI reports AUC against the reviewers, as for lighting):
  efficiency
    extra_empty      empty trips beyond one per loaded trip plus one (walking to each pick, and back at the end)
    passed_by        picks at a spot an earlier trip already walked through (within the place radius), not
                     counting the trip that leads to the pick itself
    walk_m_ratio     total walking distance / the median of recordings of the same task   (sensors only)
    walks_ratio      number of walks / the median of recordings of the same task          (sensors only)
  grouping
    trips_per_item   loaded trips / objects picked
    items_per_trip   mean objects carried on a loaded trip
    single_share     share of loaded trips carrying exactly one object
The two sensor-only signals run on every recording with sensors; the others need pick/place events.

    python3 -m procqc.signals.trips --set EVENTS SENSOR_ROOT PICKPLACE_DIR MANIFEST [--set ...] --out DIR [--gt CSV ...]
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
from pathlib import Path
from statistics import median
from typing import Dict, List, Optional, Sequence

import numpy as np

from procqc.signals.stats import auc
from procqc.signals.walk_v2 import MIN_DISP_M, load_head

PLACE_RADIUS_M = MIN_DISP_M
EFFICIENCY = ("extra_empty", "passed_by", "walk_m_ratio", "walks_ratio")
GROUPING = ("trips_per_item", "items_per_trip", "single_share")


def held_at(events: List[dict], t: float) -> List[str]:
    held: Dict[str, int] = {}
    for e in sorted(events, key=lambda e: e["t"]):
        if e["t"] > t:
            break
        o = e["object"]
        if e["action"] == "pick":
            held[o] = held.get(o, 0) + 1
        elif held.get(o, 0) > 0:
            held[o] -= 1
        else:
            held.clear()
    return sorted(o for o, n in held.items() if n > 0)


def _pos(t_arr: np.ndarray, xz: np.ndarray, t: float) -> np.ndarray:
    return xz[min(len(t_arr) - 1, int(np.searchsorted(t_arr, t)))]


def trip_log(walks: List[dict], events: List[dict], head) -> dict:
    t_arr, xz = head
    trips = [{"start": w["start"], "end": w["end"], "distance_m": w["distance_m"],
              "carrying": held_at(events, (w["start"] + w["end"]) / 2)} for w in walks]
    loaded = [x for x in trips if x["carrying"]]
    empty = len(trips) - len(loaded)
    picks = [e for e in events if e["action"] == "pick"]
    passed = 0
    for p in picks:
        pp = _pos(t_arr, xz, p["t"])
        before = [w for w in walks if w["end"] <= p["t"] + 0.5]
        for w in before[:-1]:  # the last trip before the pick is the one that leads to it
            m = (t_arr >= w["start"]) & (t_arr <= w["end"])
            if m.any() and np.linalg.norm(xz[m] - pp, axis=1).min() <= PLACE_RADIUS_M:
                passed += 1
                break
    n_obj = len({e["object"] for e in picks})
    return {"trips": trips, "n_trips": len(trips), "n_loaded": len(loaded), "n_objects": n_obj,
            "extra_empty": max(0, empty - len(loaded) - 1), "passed_by": passed,
            "trips_per_item": round(len(loaded) / n_obj, 3) if n_obj else None,
            "items_per_trip": round(float(np.mean([len(x["carrying"]) for x in loaded])), 3) if loaded else None,
            "single_share": round(sum(len(x["carrying"]) == 1 for x in loaded) / len(loaded), 3) if loaded else None}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="procqc.signals.trips")
    ap.add_argument("--set", nargs=4, action="append", required=True,
                    metavar=("EVENTS", "SENSOR_ROOT", "PICKPLACE_DIR", "MANIFEST"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--gt", nargs="*", default=[])
    a = ap.parse_args(argv)
    rows = []
    for ev_path, root, pp_dir, man in a.set:
        task = {json.loads(l)["session"]: json.loads(l)["task_id"] for l in open(man) if l.strip()}
        pp = {}
        for p in glob.glob(f"{pp_dir}/recordings/*.json"):
            r = json.load(open(p))
            pp[r["session"]] = r
        for l in open(ev_path):
            if not l.strip():
                continue
            r = json.loads(l)
            s = r["session"]
            walks = [e for e in r["events"] if e["kind"] == "walk"]
            row = {"session": s, "task_id": task.get(s, r.get("task")), "duration_s": r["duration_s"],
                   "n_walks": len(walks), "walk_m": round(sum(w["distance_m"] for w in walks), 2)}
            if s in pp:
                row.update(trip_log(walks, pp[s]["events"], load_head(Path(root) / s)))
            rows.append(row)
    by_task: Dict[str, List[dict]] = {}
    for r in rows:
        by_task.setdefault(r["task_id"], []).append(r)
    for rs in by_task.values():
        mm, mw = median(r["walk_m"] for r in rs), median(r["n_walks"] for r in rs)
        for r in rs:
            r["walk_m_ratio"] = round(r["walk_m"] / mm, 3) if mm else None
            r["walks_ratio"] = round(r["n_walks"] / mw, 3) if mw else None
    gt: Dict[str, dict] = {}
    for p in a.gt:
        for g in csv.DictReader(open(p)):
            gt[g["clip_id"]] = g
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "trips.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    summary = {"n": len(rows), "with_events": sum("n_trips" in r for r in rows)}
    for param, sigs in (("h_task_efficiency", EFFICIENCY), ("h_object_grouping", GROUPING)):
        res = {}
        for k in sigs:
            lab = [(r[k], gt[r["session"]][param]) for r in rows
                   if r.get(k) is not None and gt.get(r["session"], {}).get(param) in ("perfect", "medium", "discard")]
            pos = [v for v, h in lab if h != "perfect"]
            neg = [v for v, h in lab if h == "perfect"]
            res[k] = {"n": len(lab), "flagged": len(pos), "auc": auc(pos, neg),
                      "flagged_median": median(pos) if pos else None, "perfect_median": median(neg) if neg else None}
        summary[param[2:]] = res
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
