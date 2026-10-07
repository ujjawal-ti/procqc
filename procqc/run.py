"""Batch runner: the selected per-kind checks over a manifest of recordings.

Manifest: one JSON object per line, {"episode_id": ..., "video": <path>, "graph": <task graph file>}.
Every check of a recording shares one Episode, so the narration (one video call, cached on disk) is made
once. Each recording is written to OUT/episodes/<episode_id>.json as soon as it finishes (a re-run skips
recordings already written), with per-kind flags, review list, candidates and cost; OUT/summary.json
collects the counts and the total cost.

Usage (from the repository root):
  python3 -m procqc.run MANIFEST OUT [--kinds omission,misordering] [--workers 2] [--no-verifier]
                                     [--step-times FILE]
  --step-times: jsonl {"episode_id", "steps": {step id: [[start_s, end_s], ...]}}; replaces the
  narration's step timing for the wrong-tool check.
"""
from __future__ import annotations

import argparse
import json
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from procqc import pricing
from procqc.graph.io import load_graph
from procqc.judges import CHECKS
from procqc.judges.base import Episode, route

VERIFIED = {"omission", "misordering", "offgraph", "repeat"}  # checks with an optional video verifier
NARRATED = set(CHECKS) - {"termination"}


def run_episode(row: dict, kinds: Sequence[str], out_dir: Path, text_client, verifier: bool = True,
                step_times: Optional[dict] = None) -> dict:
    from procqc.video_client import GenAIVideoClient
    eid = row["episode_id"]
    ep = Episode(graph=load_graph(row["graph"]), video_path=row["video"], gclient=GenAIVideoClient(),
                 text_client=text_client, clip_dir=out_dir / "clips" / eid, episode_id=eid)
    total = pricing.CostMeter()
    t0 = time.time()
    res: Dict[str, dict] = {}
    by_kind: Dict[str, dict] = {}
    def narrated(k: str) -> bool:
        return k in NARRATED and not (k == "wrongtool" and step_times is not None)

    if any(narrated(k) for k in kinds):
        m = pricing.CostMeter()
        with pricing.use_meter(m):
            try:
                ep.narrated()
            except Exception as e:  # noqa: BLE001 - the narration failing fails every narrated check
                res["narration"] = {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-2000:]}
        by_kind["narration"] = m.snapshot()["total"]
        total.merge(m)
    for k in kinds:
        if narrated(k) and "narration" in res:
            res[k] = {"error": "narration failed"}
            continue
        m = pricing.CostMeter()
        with pricing.use_meter(m):
            try:
                mod = CHECKS[k]
                if k == "wrongtool":
                    r = mod.check(ep, step_times=step_times)
                elif k in VERIFIED:
                    r = mod.check(ep, verifier=verifier)
                else:
                    r = mod.check(ep)
                r.update(route(r["kind"], r["candidates"]))
                res[k] = r
            except Exception as e:  # noqa: BLE001 - one failing check does not stop the others
                res[k] = {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-2000:]}
        by_kind[k] = m.snapshot()["total"]
        total.merge(m)
    narration = ep._narrated[1] if ep._narrated else None
    snap = total.snapshot()
    return {"episode_id": eid, "video": row["video"], "graph": row["graph"],
            "duration_s": ep._duration, "checks": res, "narration": narration,
            "cost": {"total": snap["total"], "by_kind": by_kind, "by_stage": snap["by_stage"]},
            "usd": snap["total"]["usd"], "elapsed_s": round(time.time() - t0, 2)}


def summarize(results: List[dict], kinds: Sequence[str]) -> dict:
    s: Dict[str, dict] = {}
    for k in kinds:
        rs = [r["checks"].get(k, {}) for r in results]
        s[k] = {"recordings_flagged": sum(bool(x.get("flags")) for x in rs),
                "recordings_for_review": sum(bool(x.get("review")) for x in rs),
                "flags": sum(len(x.get("flags") or []) for x in rs),
                "review": sum(len(x.get("review") or []) for x in rs),
                "errors": sum("error" in x for x in rs)}
    return {"n": len(results), "kinds": s, "usd": round(sum(r["usd"] for r in results), 4),
            "latency_s": pricing.latency_stats([r["elapsed_s"] for r in results])}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="procqc.run", description=__doc__.split("\n\n")[0])
    ap.add_argument("manifest")
    ap.add_argument("out")
    ap.add_argument("--kinds", default=",".join(CHECKS), help=f"comma-separated, from {', '.join(CHECKS)}")
    ap.add_argument("--workers", type=int, default=2, help="recordings in parallel")
    ap.add_argument("--no-verifier", action="store_true", help="candidates only, no verifier video calls")
    ap.add_argument("--step-times", default=None, help="jsonl of reference step times (wrong-tool check)")
    a = ap.parse_args(argv)

    kinds = [k.strip() for k in a.kinds.split(",") if k.strip()]
    bad = [k for k in kinds if k not in CHECKS]
    if bad:
        ap.error(f"unknown kinds {bad}; choose from {list(CHECKS)}")
    from procqc.llm_client import LLMClient
    rows = [json.loads(line) for line in open(a.manifest) if line.strip()]
    times = ({json.loads(line)["episode_id"]: json.loads(line)["steps"] for line in open(a.step_times) if line.strip()}
             if a.step_times else None)
    out = Path(a.out)
    (out / "episodes").mkdir(parents=True, exist_ok=True)
    text_client = LLMClient()
    t0 = time.time()

    def one(row):
        p = out / "episodes" / f"{row['episode_id']}.json"
        if p.exists():
            return json.loads(p.read_text())
        st = None if times is None else times.get(row["episode_id"], {})
        res = run_episode(row, kinds, out, text_client, verifier=not a.no_verifier, step_times=st)
        p.write_text(json.dumps(res, indent=1, default=str))
        short = {k: (len(v.get("flags") or []), len(v.get("review") or [])) if "error" not in v else "error"
                 for k, v in res["checks"].items()}
        print(f"{row['episode_id']:20s} (flags, review)={short} {res['elapsed_s']:.0f}s ${res['usd']:.3f}", flush=True)
        return res

    with ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
        results = list(ex.map(one, rows))
    summary = summarize(results, kinds)
    summary["elapsed_s"] = round(time.time() - t0, 1)
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps(summary["kinds"], indent=1))
    print(f"${summary['usd']:.3f} total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
