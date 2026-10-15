"""Build a standalone demo page of AutoQC results on real recordings (CaptainCook4D, direct arm v2).

For every recording in a run it collects: verdict, recipe graph (steps in topological order with
prerequisites), the narration timeline with one frame per entry, the judge's findings with their
narration citations and adjudicator decisions, the ground-truth labels, and the cost split.
Everything is inlined (frames as JPEG base64) into one HTML file.

Run from the repository root:
  uv run python docs/architecture/build_qc_demo.py \
      --run out/opensource/captaincook4d/narrate --labels out/opensource/captaincook4d/labels.jsonl \
      --compare out/opensource/captaincook4d/direct_kinds_refold \
      --out docs/architecture/qc_demo_captaincook4d.html
"""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
import sys  # noqa: E402

sys.path.insert(0, str(ROOT))
from procqc.direct.narrate_judge import graph_context  # noqa: E402
from procqc.graph.io import load_graph  # noqa: E402
from procqc.signals.frames import VideoReader, to_jpeg_bytes  # noqa: E402

TEMPLATE = ROOT / "docs/architecture/qc_demo_template.html"


def b64(frame, long_edge, q):
    return base64.b64encode(to_jpeg_bytes(frame, long_edge=long_edge, quality=q)).decode("ascii")


def step_status(g, verdict, label):
    """Per graph step: performed (narrated), omitted (gold), flagged (predicted), with kinds."""
    performed = {s["label"] for s in verdict.get("segments", []) if s["label"] != "unknown"}
    gold = {}
    for f in label["findings"]:
        gold.setdefault(f.get("step"), []).append(f["kind"])
    pred = {}
    for f in verdict["findings"]:
        if f.get("final_status") in ("confirmed", "needs_human"):
            pred.setdefault(f.get("step"), []).append(f["kind"])
    out = []
    ctx, order = graph_context(g)
    for i, sid in enumerate(order, 1):
        n = g.node_map[sid]
        out.append({"pos": i, "id": sid, "text": n.description or n.name, "terminal": n.mandatory_terminal,
                    "performed": sid in performed, "gold": gold.get(sid, []), "pred": pred.get(sid, [])})
    return out, ctx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--compare", default=None, help="another run dir (e.g. the per-kind video arm) for side-by-side findings")
    ap.add_argument("--cost-runs", default="", help="comma-separated earlier run dirs whose per-stage costs are merged in "
                    "(a re-judge from cached narrations records only the judge cost; the narration was paid for in an earlier run)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="AutoQC on real recordings: CaptainCook4D, direct arm v2 (narrate then judge)")
    a = ap.parse_args()

    labels = {json.loads(l)["episode_id"]: json.loads(l) for l in Path(a.labels).read_text().splitlines() if l.strip()}
    metrics = {}
    for k in ("confirmed", "confirmed_needs_human"):
        p = Path(a.run) / f"metrics_{k}.json"
        if p.exists():
            metrics[k] = json.loads(p.read_text())
    compare = {}
    if a.compare:
        for p in Path(a.compare, "verdicts").glob("*.json"):
            v = json.loads(p.read_text())
            compare[v["episode_id"]] = [{"kind": f["kind"], "status": f.get("final_status"), "step": f.get("step"),
                                         "t": f.get("segment_start"), "conf": f.get("confidence"), "detail": f["detail"][:220]}
                                        for f in v["findings"]]
    cost_ref = {}
    for d in [x for x in a.cost_runs.split(",") if x.strip()]:
        for p in Path(d, "verdicts").glob("*.json"):
            v = json.loads(p.read_text())
            ref = cost_ref.setdefault(v["episode_id"], {})
            for k, x in v["cost"]["by_stage"].items():
                ref[k] = max(ref.get(k, 0.0), x["usd"])
    episodes = []
    graphs = {}
    for p in sorted(Path(a.run, "verdicts").glob("*.json")):
        v = json.loads(p.read_text())
        eid = v["episode_id"]
        lab = labels[eid]
        gp = v["manifest"]["graph"]
        g = graphs.setdefault(gp, load_graph(gp))
        steps, ctx = step_status(g, v, lab)
        narr = v.get("narration") or {"actions": [], "scene_start": "", "scene_end": "", "notes": ""}
        # frames: one per narration entry (small) + finding spans (larger)
        with VideoReader(v["video"]) as video:
            dur = video.duration
            for e in narr["actions"]:
                t = min(dur - 0.05, max(0.0, 0.5 * (float(e["start_s"]) + float(e["end_s"]))))
                fr = video.frame_at(t)
                e["frame"] = b64(fr, 200, 58) if fr is not None else None
            for f in v["findings"]:
                spans = []
                ev = f.get("evidence") or []
                for s in ev:
                    try:
                        x = s.replace("ctx ", "").rstrip("s").split("-")
                        spans.append((s.startswith("ctx"), float(x[0]), float(x[1])))
                    except Exception:  # noqa: BLE001
                        pass
                frames = []
                for is_ctx, s0, s1 in spans[:2]:
                    ts = np.linspace(max(0, s0 - 0.5), min(dur - 0.05, s1 + 0.5), 3)
                    for t in ts:
                        fr = video.frame_at(float(t))
                        if fr is not None:
                            frames.append({"t": round(float(t), 1), "ctx": is_ctx, "jpg": b64(fr, 300, 62)})
                f["frames"] = frames
        by_stage = {k: x["usd"] for k, x in v["cost"]["by_stage"].items()}
        for k, x in cost_ref.get(eid, {}).items():  # narration paid for in an earlier run of the same recording
            by_stage[k] = max(by_stage.get(k, 0.0), x)
        cost_total = dict(v["cost"]["total"])
        cost_total["usd"] = round(sum(by_stage.values()), 4)
        episodes.append({
            "episode_id": eid, "recipe": lab["meta"].get("recipe"), "recording_id": lab["meta"].get("recording_id"),
            "duration_s": round(dur, 1), "verdict": v["verdict"], "quality": v["quality_score"],
            "route_to_human": v["route_to_human"], "cost": cost_total,
            "cost_by_stage": {k: round(x, 4) for k, x in by_stage.items()},
            "gold": lab["findings"], "clean": lab["clean"], "steps": steps, "graph_context": ctx,
            "narration": narr, "findings": v["findings"], "calls": v.get("calls", {}),
            "compare": compare.get(eid, []),
        })
    data = {"title": a.title, "run": a.run, "compare_run": a.compare, "metrics": metrics, "episodes": episodes}
    html = TEMPLATE.read_text().replace("/*__DATA__*/", "window.QC = " + json.dumps(data) + ";")
    Path(a.out).write_text(html)
    print(f"wrote {a.out} ({Path(a.out).stat().st_size/1e6:.1f} MB), {len(episodes)} recordings, "
          f"{sum(len(e['narration']['actions']) for e in episodes)} narration frames")


if __name__ == "__main__":
    main()
