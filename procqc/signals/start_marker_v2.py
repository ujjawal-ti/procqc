"""Start-gesture search, version 2: a looser thumbs-up search near the start of a headset recording, used only
when the standard event log (procqc.signals.sensors) found no start marker.

The standard detector (left unchanged) marks a thumbs-up when, for one hand, four fingers are curled (fingertip
to palm distance / hand size < 0.62), the thumb is extended (> 0.95) and points up (vertical share of the thumb
direction > 0.35), for at least 0.25 s after 0.3 s majority smoothing; a gesture starting within 3 s of the start
is the start marker. On the 100 Meta pilot recordings it missed 3 start gestures that reviewers and frames show:
one with thumbs leaning sideways (up 0.30-0.35), two cut short because the recording began as the gesture ended
(0.1-0.3 s).

Version 2 inside the first `window_s` seconds only: thumb direction > 0.20, minimum 0.08 s, 0.1 s smoothing,
and, to keep the looser thresholds from firing on ordinary hand poses, BOTH hands must hold the pose at the same
time (the protocol's start signal is two thumbs up). Hand shape thresholds are unchanged.

Usage (from the repository root):
  python3 -m procqc.signals.start_marker_v2 SENSOR_ROOT EVENTS.jsonl OUT.jsonl [--fp-check]
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

PALM, WRIST, THUMB_META, THUMB_TIP, MID_PROX = 0, 1, 2, 5, 12
TIPS = (5, 10, 15, 20, 25)
HANDS = ("left", "right")


@dataclass
class LooseStart:
    window_s: float = 3.0
    curl_max: float = 0.62      # unchanged
    thumb_ext_min: float = 0.95  # unchanged
    thumb_up_min: float = 0.20   # standard 0.35
    min_s: float = 0.08          # standard 0.25
    smooth_s: float = 0.10       # standard 0.30
    joint_smooth_s: float = 0.05  # standard 0.15
    both_hands: bool = True      # standard: one hand is enough


def _jsonl(p: Path) -> List[dict]:
    return [json.loads(l) for l in open(p) if l.strip()]


def load_hands(folder: Path, upto_s: Optional[float] = None) -> Tuple[np.ndarray, Dict[str, Tuple[np.ndarray, np.ndarray]]]:
    t0 = json.loads((folder / "session.json").read_text())["startNs"]
    head = _jsonl(folder / "hmd.jsonl")
    raw = {s: _jsonl(folder / f"hand-{s}.jsonl") for s in HANDS}
    n = min([len(head)] + [len(r) for r in raw.values()])
    t = np.array([(h["t"] - t0) / 1e9 for h in head[:n]])
    k = n if upto_s is None else int(np.searchsorted(t, upto_s)) + 1
    hands = {s: (np.array([r.get("state") == "tracked" for r in raw[s][:k]]),
                 np.array([r["joints"] for r in raw[s][:k]], dtype=float)[:, :, :3]) for s in HANDS}
    return t[:k], hands


def _runs(mask: np.ndarray, t: np.ndarray, min_s: float) -> List[Tuple[float, float]]:
    out, i, n = [], 0, len(mask)
    while i < n:
        if not mask[i]:
            i += 1
            continue
        k = i
        while k + 1 < n and mask[k + 1]:
            k += 1
        if t[k] - t[i] >= min_s:
            out.append((float(t[i]), float(t[k])))
        i = k + 1
    return out


def _smooth_bool(m: np.ndarray, w: int) -> np.ndarray:
    if w <= 1:
        return m
    pad = w // 2
    x = np.pad(m.astype(float), pad, mode="edge")
    return np.convolve(x, np.ones(w) / w, mode="valid") > 0.5


def pose_mask(ok: np.ndarray, j: np.ndarray, hz: float, cfg: LooseStart) -> np.ndarray:
    w = max(1, int(round(cfg.joint_smooth_s * hz)) | 1)
    if w > 1 and len(j) > w:
        pad = w // 2
        jp = np.pad(j, [(pad, pad), (0, 0), (0, 0)], mode="edge")
        j = np.median(np.lib.stride_tricks.sliding_window_view(jp, w, axis=0), axis=-1)
    size = np.maximum(np.linalg.norm(j[:, MID_PROX] - j[:, WRIST], axis=1), 1e-3)
    tips = np.stack([np.linalg.norm(j[:, k] - j[:, PALM], axis=1) / size for k in TIPS], 1)
    th = j[:, THUMB_TIP] - j[:, THUMB_META]
    up = th[:, 1] / np.maximum(np.linalg.norm(th, axis=1), 1e-6)
    return ok & (tips[:, 1:].max(1) < cfg.curl_max) & (tips[:, 0] > cfg.thumb_ext_min) & (up > cfg.thumb_up_min)


def search(t: np.ndarray, hands, lo: float, hi: float, cfg: LooseStart) -> Optional[dict]:
    sel = (t >= lo) & (t <= hi)
    if sel.sum() < 3:
        return None
    ts = t[sel]
    hz = (len(ts) - 1) / max(ts[-1] - ts[0], 1e-6)
    w = max(1, int(round(cfg.smooth_s * hz)) | 1)
    masks = {s: _smooth_bool(pose_mask(hands[s][0][sel], hands[s][1][sel], hz, cfg), w) for s in HANDS}
    m = (masks["left"] & masks["right"]) if cfg.both_hands else (masks["left"] | masks["right"])
    runs = _runs(m, ts, cfg.min_s)
    if not runs:
        return None
    a, b = runs[0]
    return {"kind": "gesture", "gesture": "thumbs_up", "start": round(a, 2), "end": round(b, 2),
            "hands": [s for s in HANDS if masks[s][(ts >= a) & (ts <= b)].any()], "role": "start_marker",
            "detector": "start_marker_v2"}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="procqc.signals.start_marker_v2")
    ap.add_argument("sensor_root")
    ap.add_argument("events")
    ap.add_argument("out")
    ap.add_argument("--fp-check", action="store_true",
                    help="also run the loose search on mid-recording windows with no standard gesture (false-fire proxy)")
    a = ap.parse_args(argv)
    cfg = LooseStart()
    ev = {json.loads(l)["session"]: json.loads(l) for l in open(a.events)}
    rows, fp = [], {"windows": 0, "fires": []}
    for sid, e in sorted(ev.items()):
        std = e["markers"].get("start")
        t, hands = load_hands(Path(a.sensor_root) / sid, None if a.fp_check else cfg.window_s + 0.5)
        v2 = search(t, hands, 0.0, cfg.window_s, cfg)
        start = std or v2
        rows.append({"session": sid, "standard": std, "v2": v2, "start_marker": start,
                     "source": "standard" if std else ("start_marker_v2" if v2 else None)})
        if a.fp_check:  # windows of the same length away from the ends and from every standard gesture
            gs = [g for g in e["events"] if g["kind"] == "gesture"]
            lo = cfg.window_s + 2.0
            while lo + cfg.window_s < e["duration_s"] - cfg.window_s - 2.0:
                hi = lo + cfg.window_s
                if not any(g["start"] - 1.0 <= hi and g["end"] + 1.0 >= lo for g in gs):
                    fp["windows"] += 1
                    f = search(t, hands, lo, hi, cfg)
                    if f:
                        fp["fires"].append({"session": sid, **f})
                lo = hi
    with open(a.out, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    n = len(rows)
    print(f"start marker: standard {sum(r['standard'] is not None for r in rows)}/{n}, "
          f"with v2 fallback {sum(r['start_marker'] is not None for r in rows)}/{n}")
    print(f"v2 alone (ignoring the standard detector): {sum(r['v2'] is not None for r in rows)}/{n}")
    for r in rows:
        if r["source"] == "start_marker_v2" or (r["standard"] is None):
            print("  ", r["session"][:8], "->", r["v2"])
    if a.fp_check:
        print(f"false-fire proxy: {len(fp['fires'])} fires in {fp['windows']} mid-recording {cfg.window_s:.0f} s windows "
              f"with no standard gesture")
        Path(a.out).with_suffix(".fp.json").write_text(json.dumps(fp, indent=1))
    print("settings:", asdict(cfg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
