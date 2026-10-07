"""Scorecard: the same metrics for every kind, from a run folder and a labels file (no model calls).

Labels: one JSON object per line, {"episode_id": ..., "findings": [{"kind", "step", "start", "end",
"alt_steps"?}, ...]}, with kinds early_termination, omission, misordering, addition_offgraph,
addition_repeat, repeated_addition, wrong_tool_object. Recordings with no line count as clean.

Metrics per kind and setting:
  recording level  P = recordings with the error, Neg = without; TP = with the error and flagged,
                   FN, FP = without the error and flagged, TN; recall = TP / P,
                   false-alarm rate = FP / Neg, precision = TP / (TP + FP)
  event level      each labelled error matched at most once (greedy): TP, FP, FN, precision, recall
  settings         flags            only `flags` (what the pipeline reports as errors)
                   flags + review   `flags` and `review` (everything a human would see)
Event matching: termination one event per recording; omission and wrong tool by step id (wrong tool
also by the later steps of the same substitute); misordering by step id or a label's alt_steps; repeat
by step id and time overlap; off-graph addition by time overlap.

Usage (from the repository root):
  python3 -m procqc.evaluate RUN_DIR LABELS [--kinds omission,misordering] [--json OUT]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

TOL = 1.0  # seconds of slack for time overlap


def _ov(span, g: dict) -> bool:
    return bool(span) and span[0] <= float(g["end"]) + TOL and span[1] >= float(g["start"]) - TOL


def _steps(p: dict) -> set:
    return {x for x in (p.get("step"), *p.get("also_steps", [])) if x}


# kind -> (check name, label kind, prediction filter, match rule, one prediction may cover several labels)
SPECS: Dict[str, tuple] = {
    "early_termination": ("termination", "early_termination", None, lambda p, g: True, False),
    "omission": ("omission", "omission", None, lambda p, g: p.get("step") == g.get("step"), False),
    "misordering": ("misordering", "misordering", None,
                    lambda p, g: p.get("step") in {g.get("step"), *g.get("alt_steps", [])}, False),
    "addition_offgraph": ("offgraph", "addition_offgraph", None, lambda p, g: _ov(p.get("span_s"), g), False),
    "addition_repeat": ("repeat", "addition_repeat", lambda p: p.get("report_as", "addition_repeat") == "addition_repeat",
                        lambda p, g: p.get("step") == g.get("step") and _ov(p.get("span_s"), g), False),
    "repeated_addition": ("repeat", "repeated_addition", lambda p: p.get("report_as") == "parameter_deviation",
                          lambda p, g: p.get("step") == g.get("step") and _ov(p.get("span_s"), g), False),
    "wrong_tool_object": ("wrongtool", "wrong_tool_object", None, lambda p, g: g.get("step") in _steps(p), True),
}


def load_jsonl(path: str) -> Dict[str, dict]:
    return {r["episode_id"]: r for r in (json.loads(line) for line in open(path) if line.strip())}


def load_run(run_dir: str) -> Dict[str, dict]:
    out = {}
    for p in sorted(Path(run_dir, "episodes").glob("*.json")):
        r = json.loads(p.read_text())
        out[r["episode_id"]] = r
    return out


def predictions(result: dict, check: str, keep: Optional[Callable], with_review: bool) -> Optional[List[dict]]:
    """The predictions of one check on one recording; None if the check did not run or failed."""
    c = (result.get("checks") or {}).get(check)
    if not c or "error" in c:
        return None
    preds = list(c.get("flags") or []) + (list(c.get("review") or []) if with_review else [])
    return [p for p in preds if keep is None or keep(p)]


def evaluate(kind: str, results: Dict[str, dict], labels: Dict[str, dict], with_review: bool) -> dict:
    check, label, keep, match, several = SPECS[kind]
    rec = {"tp": 0, "fn": 0, "fp": 0, "tn": 0}
    ev = {"tp": 0, "fp": 0, "fn": 0}
    skipped = 0
    for eid, r in results.items():
        preds = predictions(r, check, keep, with_review)
        if preds is None:
            skipped += 1
            continue
        gold = [f for f in (labels.get(eid) or {}).get("findings", []) if f.get("kind") == label]
        if kind == "early_termination":
            gold, preds = gold[:1], preds[:1]  # one event per recording
        hit: set = set()
        for p in preds:
            ms = [i for i, g in enumerate(gold) if i not in hit and match(p, g)]
            if not ms:
                ev["fp"] += 1
                continue
            for i in (ms if several else ms[:1]):
                hit.add(i)
                ev["tp"] += 1
        ev["fn"] += len(gold) - len(hit)
        rec[("tp" if preds else "fn") if gold else ("fp" if preds else "tn")] += 1
    return {"recording": dict(rec, **rates(rec["tp"], rec["fp"], rec["fn"], rec["tn"])),
            "event": dict(ev, **rates(ev["tp"], ev["fp"], ev["fn"])), "skipped": skipped}


def _ratio(a: int, b: int) -> Optional[float]:
    return round(a / b, 3) if b else None


def rates(tp: int, fp: int, fn: int, tn: Optional[int] = None) -> dict:
    out = {"recall": _ratio(tp, tp + fn), "precision": _ratio(tp, tp + fp)}
    if tn is not None:
        out["false_alarm_rate"] = _ratio(fp, fp + tn)
    return out


def scorecard(results: Dict[str, dict], labels: Dict[str, dict], kinds: Sequence[str]) -> dict:
    return {k: {"flags": evaluate(k, results, labels, False), "flags + review": evaluate(k, results, labels, True)}
            for k in kinds}


def format_scorecard(card: dict) -> str:
    f = lambda x: "-" if x is None else f"{x:.2f}"  # noqa: E731
    L = [f"{'kind':20s} {'setting':15s} {'rec TP/P':>9s} {'recall':>6s} {'FP/Neg':>7s} {'FA rate':>7s} "
         f"{'ev TP':>5s} {'ev FP':>5s} {'ev FN':>5s} {'prec':>5s} {'recall':>6s}"]
    for k, by in card.items():
        for s, e in by.items():
            r, v = e["recording"], e["event"]
            L.append(f"{k:20s} {s:15s} {r['tp']:>4d}/{r['tp'] + r['fn']:<4d} {f(r['recall']):>6s} "
                     f"{r['fp']:>3d}/{r['fp'] + r['tn']:<3d} {f(r['false_alarm_rate']):>7s} "
                     f"{v['tp']:>5d} {v['fp']:>5d} {v['fn']:>5d} {f(v['precision']):>5s} {f(v['recall']):>6s}")
    return "\n".join(L)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="procqc.evaluate", description=__doc__.split("\n\n")[0])
    ap.add_argument("run_dir")
    ap.add_argument("labels")
    ap.add_argument("--kinds", default=",".join(SPECS), help=f"comma-separated, from {', '.join(SPECS)}")
    ap.add_argument("--json", default=None, help="also write the scorecard as JSON here")
    a = ap.parse_args(argv)
    kinds = [k.strip() for k in a.kinds.split(",") if k.strip()]
    bad = [k for k in kinds if k not in SPECS]
    if bad:
        ap.error(f"unknown kinds {bad}; choose from {list(SPECS)}")
    card = scorecard(load_run(a.run_dir), load_jsonl(a.labels), kinds)
    print(format_scorecard(card))
    if a.json:
        Path(a.json).write_text(json.dumps(card, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
