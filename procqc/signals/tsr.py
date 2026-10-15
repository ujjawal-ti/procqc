"""Task-Specific Requirements, free first test: do the logs we already have separate the reviewers' TSR scores?

The Snowbird rubric: every task-specific checklist requirement is followed; discard = a critical requirement is
missed. Nothing new is built here; the signals are read from existing outputs:

  item log (early-termination check, every recording)
    not_met          SOP conditions judged not met at the end moment
    at_start         items still at their starting place
    elsewhere        items moved, but not to the destination
    flagged          the check raised a finding (termination or wrong destination)
    short            fewer items handled than the lower end of the graph's repeat count ("3-5 cups" -> 3)
  narration matched to the graph (pick/place event set)
    unmatched_steps  required graph steps (not optional, not start/end) that no narrated entry matched
    offgraph_share   share of narrated entries matched to no graph step
    short_picks      fewer pick events than the lower end of the repeat count
  sensors (every recording with sensors)
    stop_miss_share  share of arrivals (end of a v2 walk) not followed by a stop of at least STOP_S. Every SOP here
                     asks to "stand still for 1 second" at the item and "stop for 1 second" at the destination,
                     but the drafted graphs do not encode it (settle_time_s is 0 everywhere), so STOP_S is read from
                     the SOP text, not from the graph. A stop = head speed below the still threshold, starting
                     within ARRIVE_S of the walk's end.
    stop_s_median    median stop length after an arrival

No thresholds: with --gt the CLI reports AUC for flagged (medium or discard) against perfect, and for discard
against the rest. Labels are only used to score.

    python3 -m procqc.signals.tsr --set MANIFEST TERMINATION_DIR PICKPLACE_DIR WALK_V2_EVENTS SENSOR_ROOT [--set ...] \
        --out DIR --gt CSV ...
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import re
from pathlib import Path
from statistics import median
from typing import Dict, List, Optional, Sequence

from procqc.signals.stats import auc

ITEM = ("not_met", "at_start", "elsewhere", "flagged", "short")
NARR = ("unmatched_steps", "offgraph_share", "short_picks")
SENS = ("stop_miss_share", "stop_s_median")
STOP_S = 1.0
ARRIVE_S = 1.0


def count_floor(g) -> Optional[int]:
    """Lower end of the first repeat block's count hint ("3-5 cups or mugs" -> 3)."""
    for rb in getattr(g, "repeat_blocks", None) or []:
        m = re.search(r"\d+", rb.count_hint or "")
        if m:
            return int(m.group())
    return None


def required_steps(g) -> List[str]:
    return [n.id for n in g.nodes if n.id not in ("start", "end") and not n.optional and not n.conditional_on]


def item_signals(t: dict, floor: Optional[int]) -> dict:
    items = t["judgement"].get("items", [])
    return {"n_items": len(items),
            "not_met": sum(c.get("answer") == "not_met" for c in t["judgement"].get("conditions", [])),
            "at_start": sum(i.get("at_end") == "at_starting_place" for i in items),
            "elsewhere": sum(i.get("at_end") == "elsewhere" for i in items),
            "flagged": int(any(f.get("final_status", f.get("status")) not in (None, "none", "pass") for f in t.get("findings", []))),
            "short": int(floor is not None and len(items) < floor)}


def narr_signals(pp: dict, g, floor: Optional[int]) -> dict:
    acts = pp["narration"].get("actions", [])
    matched = {s for a in acts for s in (a.get("matched_step_ids") or ([a["matched_step_id"]] if a.get("matched_step_id") else []))}
    req = required_steps(g)
    picks = sum(e["action"] == "pick" for e in pp["events"])
    return {"unmatched_steps": sum(s not in matched for s in req), "unmatched_ids": [s for s in req if s not in matched],
            "offgraph_share": round(sum(not (a.get("matched_step_ids") or a.get("matched_step_id")) for a in acts) / len(acts), 3) if acts else None,
            "short_picks": int(floor is not None and picks < floor), "picks": picks}


def stop_signals(walks: List[dict], head) -> dict:
    import numpy as np
    from procqc.signals.walk_v2 import HEAD_SMOOTH_S, STILL_SPEED, _smooth
    t, xz = head
    hz = (len(t) - 1) / max(1e-6, t[-1] - t[0])
    p = _smooth(xz, max(1, int(round(HEAD_SMOOTH_S * hz))))
    still = np.linalg.norm(np.gradient(p, axis=0) / np.gradient(t)[:, None], axis=1) < STILL_SPEED
    stops = []
    for w in walks:
        i = int(np.searchsorted(t, w["end"]))
        j = int(np.searchsorted(t, w["end"] + ARRIVE_S))
        k = next((x for x in range(i, min(j, len(t))) if still[x]), None)
        if k is None:
            stops.append(0.0)
            continue
        e = k
        while e + 1 < len(t) and still[e + 1]:
            e += 1
        stops.append(float(t[e] - t[k]))
    return {"arrivals": len(stops), "stop_miss_share": round(sum(x < STOP_S for x in stops) / len(stops), 3) if stops else None,
            "stop_s_median": round(-median(stops), 3) if stops else None}  # negated so that higher = worse


def main(argv: Optional[Sequence[str]] = None) -> int:
    from procqc.judges.termination_v2 import load_graph
    ap = argparse.ArgumentParser(prog="procqc.signals.tsr")
    ap.add_argument("--set", nargs=5, action="append", required=True,
                    metavar=("MANIFEST", "TERMINATION_DIR", "PICKPLACE_DIR", "WALK_V2_EVENTS", "SENSOR_ROOT"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--gt", nargs="*", default=[])
    a = ap.parse_args(argv)
    graphs: Dict[str, object] = {}
    rows = []
    for man, term, ppd, evp, root in a.set:
        sens = {json.loads(l)["session"]: json.loads(l) for l in open(evp) if l.strip()}
        pp = {json.load(open(p))["session"]: json.load(open(p)) for p in glob.glob(f"{ppd}/recordings/*.json")}
        for l in open(man):
            if not l.strip():
                continue
            m = json.loads(l)
            tp = Path(term) / "recordings" / f"{m['session']}.json"
            if not tp.exists():
                continue
            g = graphs.setdefault(m["graph"], load_graph(m["graph"]))
            floor = count_floor(g)
            t = json.loads(tp.read_text())
            row = {"session": m["session"], "task_id": m["task_id"], "duration_s": m.get("duration_s"), "count_floor": floor,
                   **item_signals(t, floor)}
            if m["session"] in pp:
                row.update(narr_signals(pp[m["session"]], g, floor))
            if m["session"] in sens and (Path(root) / m["session"] / "hmd.jsonl").exists():
                from procqc.signals.walk_v2 import load_head
                walks = [e for e in sens[m["session"]]["events"] if e["kind"] == "walk"]
                row.update(stop_signals(walks, load_head(Path(root) / m["session"])))
            rows.append(row)
    gt: Dict[str, str] = {}
    for p in a.gt:
        for r in csv.DictReader(open(p)):
            gt[r["clip_id"]] = r.get("h_task_specific_requirements", "")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "tsr.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps({**r, "h": gt.get(r["session"], "")}) + "\n")

    def score(sub: List[dict]) -> dict:
        res = {}
        for k in ITEM + NARR + SENS:
            lab = [(r[k], gt[r["session"]]) for r in sub if r.get(k) is not None and gt.get(r["session"]) in ("perfect", "medium", "discard")]
            fl = [v for v, h in lab if h != "perfect"]
            pf = [v for v, h in lab if h == "perfect"]
            dc = [v for v, h in lab if h == "discard"]
            nd = [v for v, h in lab if h != "discard"]
            res[k] = {"n": len(lab), "flagged": len(fl), "auc_flagged": auc(fl, pf), "discard": len(dc), "auc_discard": auc(dc, nd),
                      "mean_flagged": round(sum(fl) / len(fl), 2) if fl else None, "mean_perfect": round(sum(pf) / len(pf), 2) if pf else None}
        return res

    ok = [r for r in rows if (r.get("duration_s") or 0) >= 10]
    summary = {"n": len(rows), "all": score(rows), "without_short_fragments": score(ok)}
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary["all"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
