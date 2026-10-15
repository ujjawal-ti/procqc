"""Collect the real artifacts of one QC episode into a single JSON file for the
interactive architecture page (docs/architecture/index.html).

Everything here is read from files the pipeline already produced or computed
deterministically (motion signal, symbolic verification, lint). No LLM calls.

Run from the repository root:
    uv run python docs/architecture/build_demo_data.py
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from procqc.graph import ops  # noqa: E402
from procqc.graph.io import load_graph, to_mermaid  # noqa: E402
from procqc.graph.linter import lint  # noqa: E402
from procqc.pipeline import PipelineOptions, make_proposal  # noqa: E402
from procqc.signals.frames import VideoReader, laplacian_sharpness, sample_times, to_jpeg_bytes  # noqa: E402
from procqc.signals.frames import motion_activity  # noqa: E402

EPISODE = "hairdryer_trunc44"
VERDICT = ROOT / "out/audit_demo3/verdicts" / f"{EPISODE}.json"
RUN_SUMMARY = ROOT / "out/audit_demo3/run_summary.json"
GRAPH = ROOT / "out/hairdryer_graph.yaml"
SOP = ROOT / "out/hairdryer_sop.md"
EXPORT_DIR = ROOT / "out/laya_training_export"
OUT = ROOT / "docs/architecture/demo_data.json"

LONG_EDGE = 360
QUALITY = 68


def jpeg_b64(frame, long_edge=LONG_EDGE, quality=QUALITY) -> str:
    return base64.b64encode(to_jpeg_bytes(frame, long_edge=long_edge, quality=quality)).decode("ascii")


def main() -> None:
    verdict = json.loads(VERDICT.read_text())
    run_summary = json.loads(RUN_SUMMARY.read_text())
    g = load_graph(GRAPH)
    opts = PipelineOptions(**{k: v for k, v in verdict["options"].items() if k != "router"})

    # ---- task graph: nodes, edges, lint, mermaid -------------------------------------------
    nodes = []
    for n in g.nodes:
        nodes.append({
            "id": n.id, "name": n.name, "kind": n.kind, "description": n.description,
            "preconditions": [str(p) for p in n.preconditions],
            "effects": [str(p) for p in n.effects],
            "mandatory_terminal": n.mandatory_terminal, "permitted_repeats": n.permitted_repeats,
            "start_rule": n.start_rule, "end_rule": n.end_rule, "pitfalls": list(n.pitfalls),
        })
    edges = [{"source": e.source, "target": e.target, "relation": str(e.relation.value if hasattr(e.relation, 'value') else e.relation),
              "guidance": e.guidance} for e in g.edges]
    lint_issues = [{"code": i.code, "level": i.level, "message": i.message} for i in lint(g)]

    # ---- symbolic verification of the localized sequence ---------------------------------
    seq = verdict["step_sequence"]
    vr = ops.verify_sequence(g, seq)
    symbolic = {
        "sequence": seq,
        "ok": vr.ok,
        "violations": [{"kind": v.kind, "index": v.index, "step": v.step, "detail": v.detail, "missing": v.missing}
                       for v in vr.violations],
        "completed": vr.completed,
        "final_state": vr.final_state,
        "impact": vr.impact,
        "executable_after_each": [],
    }
    # executable set after each prefix (what the localizer's candidate list is built from)
    for i in range(len(seq) + 1):
        prefix = seq[:i]
        try:
            ex = sorted(ops.executable_set(g, prefix))
        except Exception:  # pragma: no cover
            ex = []
        symbolic["executable_after_each"].append({"after": prefix[-1] if prefix else None, "executable": ex})

    # ---- video, motion signal, boundary proposals -----------------------------------------
    video = VideoReader(str(ROOT / verdict["video"]))
    sig = motion_activity(video.path)
    proposal = make_proposal(opts.proposer, video, opts)
    # downsample the signal for plotting
    step = max(1, len(sig.t) // 260)
    signal = {"t": [round(float(x), 2) for x in sig.t[::step]],
              "v": [round(float(x), 4) for x in sig.value[::step]],
              "dt": float(sig.dt), "source": sig.source}
    windows = [{"start": round(a, 3), "end": round(b, 3)} for a, b in proposal.segments]
    candidates = [round(float(c), 3) for c in proposal.candidates]

    # ---- frames -------------------------------------------------------------------------------
    frames: dict = {}

    def grab(key: str, times, long_edge=LONG_EDGE):
        out = []
        for t in times:
            fr = video.frame_at(float(t))
            if fr is None:
                continue
            out.append({"t": round(float(t), 2), "jpg": jpeg_b64(fr, long_edge), "sharp": round(laplacian_sharpness(fr), 1)})
        frames[key] = out

    # the raw input: a strip across the whole clip
    grab("input_strip", np.linspace(0.3, video.duration - 0.3, 12), long_edge=240)
    # localizer windows: 3 frames per proposed window (same sampling as the scorer)
    for i, (a, b) in enumerate(proposal.segments):
        grab(f"window_{i}", sample_times(a, b, opts.frames_per_window), long_edge=200)
    # refinement strip around the coil->open-drawer join (largest confidence drop)
    join = 40.0
    grab("refine_strip", np.linspace(join - opts.refine_span_s, join + opts.refine_span_s, opts.refine_frames), long_edge=220)
    # effect frames actually used by the checker (from predicate_checks.frame_times)
    seen = set()
    for c in verdict["predicate_checks"]:
        key = c["step"]
        if key in seen:
            continue
        seen.add(key)
        grab(f"effect_{key}", c["frame_times"], long_edge=260)
    # adjudicator evidence frames
    for k, f in enumerate(verdict["findings"]):
        adj = f.get("adjudication") or {}
        if adj.get("evidence_times"):
            grab(f"adjudicate_{k}", adj["evidence_times"], long_edge=260)
    video.close()

    # ---- training export samples ----------------------------------------------------------
    export_summary = json.loads((EXPORT_DIR / "export_summary.json").read_text())
    samples = []
    seen_src = set()
    for line in (EXPORT_DIR / "train.jsonl").read_text().splitlines():
        r = json.loads(line)
        if EPISODE.split("_")[0] not in r.get("state_text", "").lower() and "hair dryer" not in r.get("state_text", ""):
            continue
        src = r.get("source")
        if src in seen_src:
            continue
        seen_src.add(src)
        rr = {k: v for k, v in r.items() if k not in ("image", "images")}
        imgs = r.get("images") or ([r["image"]] if r.get("image") else [])
        rr["n_images"] = len(imgs)
        rr["thumb"] = imgs[0] if imgs else None  # already base64 jpeg
        samples.append(rr)
        if len(samples) >= 5:
            break

    # ---- other episodes in the same batch ---------------------------------------------
    others = []
    for p in sorted((ROOT / "out/audit_demo3/verdicts").glob("*.json")):
        v = json.loads(p.read_text())
        others.append({
            "episode_id": v["episode_id"], "task_id": v["task_id"], "verdict": v["verdict"],
            "quality_score": v["quality_score"], "n_findings": len(v["findings"]),
            "steps": v["step_sequence"], "usd": v["cost"]["total"]["usd"], "calls": v["cost"]["total"]["calls"],
            "cache_hits": v["cost"]["total"]["cache_hits"], "segments": v["segments"],
        })

    data = {
        "episode": {
            "id": EPISODE, "task_id": verdict["task_id"], "video": verdict["video"],
            "duration_s": round(video.duration, 2), "fps": round(video.info.fps, 2) if hasattr(video, "info") else None,
            "width": video.info.width if hasattr(video, "info") else None,
            "height": video.info.height if hasattr(video, "info") else None,
            "note": "The full recording (55 s) was cut at 44 s to simulate a recording that stops before the drawer is closed.",
        },
        "sop": SOP.read_text(),
        "graph": {"task_id": g.task_id, "name": g.name, "description": g.description,
                  "objects": [{"id": o.id, "name": o.name, "category": o.category} for o in g.objects],
                  "initial_state": [str(p) for p in g.initial_state], "goal": [str(p) for p in g.goal],
                  "nodes": nodes, "edges": edges, "lint": lint_issues, "mermaid": to_mermaid(g),
                  "provenance": g.provenance.model_dump() if g.provenance else None},
        "options": verdict["options"],
        "signal": signal, "windows": windows, "candidates": candidates,
        "localization": verdict["localization"],
        "segments": verdict["segments"],
        "symbolic": symbolic,
        "predicate_checks": verdict["predicate_checks"],
        "findings": verdict["findings"],
        "verdict": {k: verdict[k] for k in ("verdict", "quality_score", "route_to_human", "route_reasons", "counts", "usage", "timing_s", "created_at", "schema_version")},
        "cost": verdict["cost"],
        "frames": frames,
        "export": {"summary": export_summary, "samples": samples},
        "run_summary": run_summary,
        "episodes": others,
    }
    if len(sys.argv) > 1:
        data["dashboard_url"] = sys.argv[1]  # e.g. http://localhost:5173 from /understand-dashboard

    payload = json.dumps(data)
    OUT.write_text(payload)
    # sidecar consumed by index.html (works from file:// without a server)
    js = OUT.with_name("demo_data.js")
    js.write_text("window.DEMO = " + payload + ";\n")
    # single-file copy for sharing with stakeholders
    html = OUT.with_name("index.html").read_text()
    standalone = OUT.with_name("procqc_pipeline_walkthrough.html")
    standalone.write_text(html.replace('<script src="demo_data.js"></script>',
                                       "<script>window.DEMO = " + payload + ";</script>"))
    print(f"wrote {OUT.name} ({OUT.stat().st_size/1e6:.1f} MB), {js.name}, {standalone.name} "
          f"({standalone.stat().st_size/1e6:.1f} MB); frames: "
          + ", ".join(f"{k}={len(v)}" for k, v in frames.items()))
    print("windows:", len(windows), "lint:", len(lint_issues), "violations:", len(symbolic["violations"]))


if __name__ == "__main__":
    main()
