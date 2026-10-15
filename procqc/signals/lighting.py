"""Lighting: brightness and contrast statistics per recording (pixels only, no model call).

The Snowbird rubric's lighting parameter asks whether the hands, objects and room are clearly visible. Too dark,
too bright (glare, a window behind the task) and flat low-contrast footage all hide them, so each sampled frame
records its mean brightness, its spread (RMS contrast), its share of near-black pixels and its share of clipped
white pixels, on the grey image. The recording keeps the median frame and the worst 10 % of frames, because a
recording can be well lit overall and still have a dark stretch where the task happens.

No thresholds yet: the CLI writes the statistics and, with --gt, how well each one separates the recordings that
reviewers scored medium or discard (AUC). Thresholds follow from that, not from guesses.

    python3 -m procqc.signals.lighting MANIFEST OUT [--gt ground_truth.csv] [--fps 1] [--workers 4]
"""
from __future__ import annotations

import argparse
import csv
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import cv2
import numpy as np

from procqc.signals.frames import VideoReader, resize_long_edge
from procqc.signals.stats import auc

FPS = 1.0
DARK = 40      # grey level counted as near-black (0-255)
CLIP = 250     # grey level counted as clipped white
WORST = 0.10   # share of frames kept as the recording's worst stretch
STATS = ("mean", "contrast", "dark_frac", "clip_frac")


def frame_stats(frame: np.ndarray) -> Dict[str, float]:
    g = cv2.cvtColor(resize_long_edge(frame, 360), cv2.COLOR_BGR2GRAY).astype(np.float32)
    return {"mean": float(g.mean()), "contrast": float(g.std()), "dark_frac": float((g < DARK).mean()),
            "clip_frac": float((g >= CLIP).mean())}


def recording_stats(path: str, fps: float = FPS) -> dict:
    with VideoReader(path) as v:
        times = [i / fps for i in range(int(v.duration * fps))]
        frames = [frame_stats(f) for f in v.frames_at(times) if f is not None]
    out = {"n_frames": len(frames)}
    for k in STATS:
        xs = np.array([f[k] for f in frames])
        # the bad direction: low brightness and contrast, high dark and clipped shares
        worst = np.quantile(xs, WORST) if k in ("mean", "contrast") else np.quantile(xs, 1 - WORST)
        out[k] = {"median": round(float(np.median(xs)), 4), "worst": round(float(worst), 4)}
    return out


def compare_gt(rows: List[dict], gt_csv: str) -> dict:
    gt = {r["clip_id"]: r.get("h_lighting", "") for r in csv.DictReader(open(gt_csv))}
    lab = [(r, gt.get(r["session"], "")) for r in rows]
    lab = [(r, h) for r, h in lab if h in ("perfect", "medium", "discard")]
    flagged = [r for r, h in lab if h != "perfect"]
    clean = [r for r, h in lab if h == "perfect"]
    res = {"n": len(lab), "flagged": len(flagged), "auc": {}}
    for k in STATS:
        sign = -1 if k in ("mean", "contrast") else 1  # orient so higher = worse lighting
        for part in ("median", "worst"):
            res["auc"][f"{k}_{part}"] = auc([sign * r[k][part] for r in flagged], [sign * r[k][part] for r in clean])
    res["flagged_sessions"] = [{"session": r["session"], "h": h, **{k: r[k] for k in STATS}} for r, h in lab if h != "perfect"]
    return res


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="procqc.signals.lighting")
    ap.add_argument("manifest")
    ap.add_argument("out")
    ap.add_argument("--gt", default=None)
    ap.add_argument("--fps", type=float, default=FPS)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(argv)
    rows = [json.loads(l) for l in open(a.manifest) if l.strip()]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    def one(row):
        return {"session": row["session"], "task_id": row["task_id"], **recording_stats(row["video"], a.fps)}

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        res = list(ex.map(one, rows))
    with open(out / "lighting.jsonl", "w") as f:
        for r in res:
            f.write(json.dumps(r) + "\n")
    summary = {"n": len(res), "fps": a.fps}
    if a.gt:
        summary["gt"] = compare_gt(res, a.gt)
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps({k: v for k, v in summary.items() if k != "gt"} | ({"auc": summary["gt"]["auc"], "flagged": summary["gt"]["flagged"]} if a.gt else {})))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
