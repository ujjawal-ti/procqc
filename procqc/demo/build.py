"""Build the review demo: a static site over one or more run folders (no model calls).

Config (JSON):
  {"title": "...",
   "datasets": [{"name": "...", "run_dir": <procqc.run output>, "labels": <labels.jsonl>, "manifest": <manifest.jsonl>,
                 "note": "...",
                 "splits": {"<kind>" or "*": {"<episode_id>": "<split name>"}}}]}
`splits` is optional: recordings without a split are in "all". Kinds are the scorecard kinds of
procqc.evaluate.SPECS. Labels are optional per recording (a recording with no line counts as clean).

Output: OUT/index.html (the viewer), OUT/data.js (every recording, event and metric) and OUT/videos.json
(video id -> local path, read by procqc.demo.serve; videos are never copied).

Usage (from the repository root):
  python3 -m procqc.demo.build CONFIG OUT
  python3 -m procqc.demo.serve OUT
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from procqc import evaluate as E
from procqc.graph.io import load_graph

HERE = Path(__file__).resolve().parent

KINDS = {  # scorecard kind -> (menu title, one-line definition)
    "early_termination": ("Early termination", "The recording ends before the procedure's final step is done."),
    "omission": ("Omission", "A required step is never performed, although a later step that needs it is."),
    "misordering": ("Misordering", "A step is performed before a step it requires."),
    "addition_offgraph": ("Off-graph addition", "An action that is no step of the procedure and serves none."),
    "addition_repeat": ("Redundant repeat", "A step performed again, beyond what the procedure allows, with no need to redo it."),
    "repeated_addition": ("Repeated addition", "A step that states an amount performed again: the amount is wrong "
                                               "(reported as a parameter deviation)."),
    "wrong_tool_object": ("Wrong tool / object", "Another item than the step specifies is used in its role."),
}
ROUTERS = {"omission", "misordering"}  # verifier rejections go to human review (procqc.judges.base)
FIELDS = ("detail", "specified", "used", "relation", "votes", "role", "prerequisite", "dependent", "occurrence",
          "allowed", "reason", "note", "routed", "report_as", "sources")
MAX_TEXT = 600


def _short(v):
    if isinstance(v, str):
        return v[:MAX_TEXT]
    if isinstance(v, (list, tuple)):
        return [_short(x) for x in v[:12]]
    if isinstance(v, dict):
        return {k: _short(x) for k, x in list(v.items())[:20]}
    return v


def _span(c: dict) -> Optional[List[float]]:
    for k in ("span_s", "gap_s"):
        if isinstance(c.get(k), (list, tuple)) and len(c[k]) == 2:
            return [round(float(c[k][0]), 2), round(float(c[k][1]), 2)]
    if c.get("start_s") is not None:
        return [round(float(c["start_s"]), 2), round(float(c.get("end_s", c["start_s"])), 2)]
    return None


def _event(c: dict, status: str, steps: Dict[str, str]) -> dict:
    v = c.get("verification") if isinstance(c.get("verification"), dict) else {}
    answers = {k: _short(x) for k, x in v.items() if k not in ("explanation", "clips_s") and not isinstance(x, (dict, list))}
    return {"status": status, "step": c.get("step"), "step_text": steps.get(c.get("step") or "", ""),
            "span": _span(c), "fields": {k: _short(c[k]) for k in FIELDS if c.get(k) not in (None, "", [])},
            "explanation": _short(v.get("explanation") or ""), "verifier": answers,
            "evidence": _short(c.get("evidence") or []), "verifier_status": c.get("status")}


def costs(result: dict, check: str, c: dict) -> tuple:
    """(the check's own cost, the shared narration cost it relies on or None), from the run's cost.by_kind."""
    by = (result.get("cost") or {}).get("by_kind") or {}
    own = (by.get(check) or {}).get("usd", c.get("usd"))
    uses_narration = check != "termination" and c.get("timing") != "reference"
    narr = (by.get("narration") or {}).get("usd") if uses_narration else None
    return own, narr


def kind_view(kind: str, result: dict, label: Optional[dict], steps: Dict[str, str]) -> Optional[dict]:
    """One recording, one kind: events with status and ground-truth outcome; None if the check did not run."""
    check, lab, keep, match, _ = E.SPECS[kind]
    c = (result.get("checks") or {}).get(check)
    if not c:
        return None
    if "error" in c:
        return {"ran": True, "error": c["error"][:300], "events": [], "verdict": "error"}
    m = E.match_recording(kind, result, label, with_review=True)
    gold = m["gold"]
    flag_ids = {id(p) for p in c.get("flags") or []}
    events = []
    for p, ms in m["preds"]:
        e = _event(p, "flagged" if id(p) in flag_ids else "review", steps)
        e["matches"], e["outcome"] = ms, ("match" if ms else ("no_label" if not gold else "false_alarm"))
        events.append(e)
    shown = {_sig(p) for p in (c.get("flags") or []) + (c.get("review") or [])}
    for p in c.get("candidates") or []:  # what the verifier dropped (filter kinds) stays visible
        if _sig(p) in shown or (keep and not keep(p)) or p.get("status") != "rejected":
            continue
        e = _event(p, "dropped", steps)
        e["matches"] = [i for i, g in enumerate(gold) if match(p, g)]
        e["outcome"] = "would_match" if e["matches"] else None
        events.append(e)
    events.sort(key=lambda e: (e["span"] or [1e9])[0])
    own, narr = costs(result, check, c)
    active = [e for e in events if e["status"] in ("flagged", "review")]
    verdict = "flagged" if any(e["status"] == "flagged" for e in active) else ("review" if active else "clean")
    return {"ran": True, "verdict": verdict, "events": events,
            "gold": [{"step": g.get("step"), "step_text": steps.get(g.get("step") or "", ""),
                      "span": [g["start"], g["end"]] if g.get("start") is not None else None, "note": g.get("note", ""),
                      "hit": i in m["hit"]} for i, g in enumerate(gold)],
            "has_error": bool(gold), "usd": own, "narration_usd": narr}


def cost_summary(recs: List[dict], k: str) -> dict:
    """Own cost of the check, the shared narration it relies on, and the two per recording and per minute."""
    own = [x["kinds"][k]["usd"] for x in recs if x["kinds"][k].get("usd") is not None]
    narr = [x["kinds"][k]["narration_usd"] for x in recs if x["kinds"][k].get("narration_usd") is not None]
    minutes = sum(float(x["duration"] or 0) for x in recs) / 60
    r = lambda v: round(v, 4)  # noqa: E731
    return {"usd_total": r(sum(own)) if own else None, "n_costed": len(own),
            "usd_per_recording": r(sum(own) / len(own)) if own else None,
            "usd_per_minute": r(sum(own) / minutes) if own and minutes else None,
            "narration_usd_per_recording": r(sum(narr) / len(narr)) if narr else None,
            "narration_usd_total": r(sum(narr)) if narr else None,
            "minutes": round(minutes, 1)}


def _sig(c: dict) -> str:
    """Content identity of a candidate (a saved run holds separate copies in flags, review and candidates)."""
    return json.dumps({k: v for k, v in c.items() if k != "routed"}, sort_keys=True, default=str)


def _vid(path: str) -> str:
    return hashlib.sha1(path.encode()).hexdigest()[:12]


def build(config: dict, out: Path) -> dict:
    recs: List[dict] = []
    videos: Dict[str, str] = {}
    metrics: List[dict] = []
    datasets = []
    for ds in config["datasets"]:
        name = ds["name"]
        results = E.load_run(ds["run_dir"])
        labels = E.load_jsonl(ds["labels"]) if ds.get("labels") else {}
        manifest = E.load_jsonl(ds["manifest"])
        splits = ds.get("splits") or {}
        graphs: Dict[str, object] = {}
        for eid, r in sorted(results.items()):
            row = manifest.get(eid, {})
            gp = row.get("graph") or r.get("graph")
            if gp and gp not in graphs:
                graphs[gp] = load_graph(gp)
            g = graphs.get(gp)
            steps = {n.id: (n.description or n.name) for n in g.nodes if n.is_step} if g else {}
            video = row.get("video") or r.get("video")
            vid = _vid(str(Path(video).resolve())) if video else None
            if vid:
                videos[vid] = str(Path(video).resolve())
            label = labels.get(eid)
            kinds = {}
            for k in KINDS:
                kv = kind_view(k, r, label, steps)
                if kv:
                    kv["split"] = (splits.get(k) or {}).get(eid) or (splits.get("*") or {}).get(eid) or "all"
                    kinds[k] = kv
            recs.append({"id": f"{name}/{eid}", "dataset": name, "episode_id": eid, "video": vid,
                         "duration": r.get("duration_s") or (label or {}).get("duration"),
                         "task": g.name if g else "", "steps": [[s, t] for s, t in steps.items()],
                         "labels": [{"kind": f.get("kind"), "step": f.get("step"),
                                     "step_text": steps.get(f.get("step") or "", ""),
                                     "span": [f["start"], f["end"]] if f.get("start") is not None else None,
                                     "note": _short(f.get("note", ""))} for f in (label or {}).get("findings", [])],
                         "kinds": kinds})
        for k in KINDS:
            ran = {eid: r for eid, r in results.items() if f"{name}/{eid}" in {x["id"] for x in recs if k in x["kinds"]}}
            if not ran:
                continue
            by_split: Dict[str, Dict[str, dict]] = {"all": ran}
            for eid in ran:
                s = next(x["kinds"][k]["split"] for x in recs if x["id"] == f"{name}/{eid}")
                by_split.setdefault(s, {})[eid] = ran[eid]
            for s, rs in by_split.items():
                sel = [x for x in recs if x["dataset"] == name and x["episode_id"] in rs]
                metrics.append({"kind": k, "dataset": name, "split": s, "n": len(rs), **cost_summary(sel, k),
                                "flags": E.evaluate(k, rs, labels, False),
                                "flags + review": E.evaluate(k, rs, labels, True)})
        datasets.append({"name": name, "note": ds.get("note", "")})
    data = {"title": config.get("title", "procqc review demo"), "kinds": {k: {"title": t, "definition": d,
            "router": k in ROUTERS} for k, (t, d) in KINDS.items()}, "datasets": datasets, "recordings": recs,
            "metrics": metrics, "notes": config.get("notes", [])}
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy(HERE / "index.html", out / "index.html")
    (out / "data.js").write_text("window.DEMO = " + json.dumps(data, separators=(",", ":"), default=str) + ";\n")
    (out / "videos.json").write_text(json.dumps(videos, indent=1))
    return data


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="procqc.demo.build", description=__doc__.split("\n\n")[0])
    ap.add_argument("config")
    ap.add_argument("out")
    a = ap.parse_args(argv)
    data = build(json.loads(Path(a.config).read_text()), Path(a.out))
    n_ev = sum(len(kv["events"]) for r in data["recordings"] for kv in r["kinds"].values())
    print(f"{len(data['recordings'])} recordings, {n_ev} events, {len(data['metrics'])} metric rows -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
