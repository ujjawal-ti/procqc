"""Navigation and manipulation: does the operator finish picking or placing before walking?

The Snowbird rubric: "Navigation and manipulation are separate, sequential actions. Complete the object
manipulation (picking up/placing) before starting to walk to the destination." Medium = occasional minor
deviation; discard = repeatedly combines them.

Two signals per recording, both free:
  sensor   from the sensor log only. A walk that overlaps a bend (reaching down to pick or place) by at least
           MIN_OVERLAP_S, or a walk that overlaps a grip. Grip closure is unreliable and bends only appear for
           low objects, so this misses table-height pick/place.
  events   from the pick/place events (procqc.signals.pickplace): a pick or place whose narrated time falls
           inside a sensor walk. This covers every height, but narrated times are only as precise as the
           narration.

No thresholds yet: with --gt the CLI reports how well each count separates the recordings reviewers scored
medium or discard (AUC), as for lighting.

    python3 -m procqc.signals.nav_manip SENSOR_EVENTS OUT [--pickplace DIR ...] [--gt ground_truth.csv ...]
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from procqc.signals.stats import auc

MIN_OVERLAP_S = 0.3


def _ov(a: dict, b: dict) -> float:
    return max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))


def sensor_signal(events: List[dict]) -> dict:
    walks = [e for e in events if e["kind"] == "walk"]
    bends = [e for e in events if e["kind"] == "bend"]
    grips = [e for e in events if e["kind"] == "grip"]
    wb = [{"walk": [w["start"], w["end"]], "bend": [b["start"], b["end"]], "overlap_s": round(_ov(w, b), 2)}
          for w in walks for b in bends if _ov(w, b) >= MIN_OVERLAP_S]
    wg = sum(1 for w in walks for g in grips if _ov(w, g) >= MIN_OVERLAP_S)
    return {"walks": len(walks), "bends": len(bends), "walk_bend": len(wb), "walk_grip": wg, "walk_bend_cases": wb}


def event_signal(rec: dict) -> dict:
    ev = rec.get("events", [])
    at_walk = [{"t": e["t"], "action": e["action"], "object": e["object"], "walk": e["sensor"]["walk"]}
               for e in ev if e["sensor"]["walking"]]
    return {"events": len(ev), "at_walk": len(at_walk), "at_walk_share": round(len(at_walk) / len(ev), 3) if ev else None,
            "at_walk_cases": at_walk}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="procqc.signals.nav_manip")
    ap.add_argument("events", nargs="+", help="sensor event logs (jsonl)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--pickplace", nargs="*", default=[], help="pickplace output dirs")
    ap.add_argument("--gt", nargs="*", default=[])
    a = ap.parse_args(argv)
    sensors = {}
    for p in a.events:
        for l in open(p):
            if l.strip():
                r = json.loads(l)
                sensors[r["session"]] = r
    pp: Dict[str, dict] = {}
    for d in a.pickplace:
        for p in glob.glob(f"{d}/recordings/*.json"):
            r = json.load(open(p))
            pp[r["session"]] = r
    gt: Dict[str, str] = {}
    for p in a.gt:
        for r in csv.DictReader(open(p)):
            gt[r["clip_id"]] = r.get("h_navigation_manipulation", "")
    rows = []
    for s, r in sensors.items():
        row = {"session": s, "h": gt.get(s, ""), "sensor": sensor_signal(r.get("events", []))}
        if s in pp:
            row["events"] = event_signal(pp[s])
        rows.append(row)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "nav_manip.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    def sep(sub: List[dict], key) -> dict:
        lab = [r for r in sub if r["h"] in ("perfect", "medium", "discard")]
        pos = [key(r) for r in lab if r["h"] != "perfect"]
        neg = [key(r) for r in lab if r["h"] == "perfect"]
        return {"n": len(lab), "flagged": len(pos), "auc": auc(pos, neg),
                "flagged_mean": round(sum(pos) / len(pos), 2) if pos else None,
                "perfect_mean": round(sum(neg) / len(neg), 2) if neg else None}

    with_ev = [r for r in rows if "events" in r]
    summary = {"n": len(rows),
               "sensor_walk_bend": sep(rows, lambda r: r["sensor"]["walk_bend"]),
               "sensor_walk_bend_or_grip": sep(rows, lambda r: r["sensor"]["walk_bend"] + r["sensor"]["walk_grip"]),
               "events_at_walk": sep(with_ev, lambda r: r["events"]["at_walk"]),
               "events_at_walk_share": sep(with_ev, lambda r: r["events"]["at_walk_share"] or 0.0)}
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
