"""Walk detection v2: a walk is the head moving from one place to another, not the head moving fast.

The standard event log (procqc.signals.sensors) calls a walk any stretch where the horizontal
head speed stays above 0.35 m/s for 0.5 s. Slow walkers never reach that: on Set B, 14 of 67 recordings have no walk
at all although the head travels 2-22 m and the frames show the operator walking between places.

v2 keys on displacement instead of speed:
  moving   horizontal head speed above STILL_SPEED (the standard log's own "still" threshold), with gaps shorter
           than MERGE_GAP_S bridged so one walk with a brief pause stays one walk
  walk     a moving stretch whose NET horizontal displacement (first to last position) is at least MIN_DISP_M
           (the standard log's place radius: moving less than that is staying at the same place)
Net displacement, not path length, so turning on the spot, leaning and head sway do not count.
The low speed threshold leaves loose edges (the head starts drifting while a gesture is still held), so each walk
is trimmed to the stretch between the last moment the head is still within SPOT_M of its starting position and the
first moment it is within SPOT_M of its final position. SPOT_M = STILL_SPEED x STILL_MIN_S, how far a head the
standard log calls still can drift.

The other events (gesture, bend, still, grip) are copied unchanged; only "walk" is replaced, and each event log
gets "walk_version": 2. v1 output is never touched (version, don't patch).

    python3 -m procqc.signals.walk_v2 EVENTS_JSONL SENSOR_ROOT OUT_JSONL
SENSOR_ROOT holds one folder per session (session.json, hmd.jsonl).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np

HEAD_SMOOTH_S = 0.3   # as the standard log
STILL_SPEED = 0.12    # m/s, the standard log's still threshold
MERGE_GAP_S = 0.3
MIN_DISP_M = 0.5      # the standard log's place radius
STILL_MIN_S = 0.5     # the standard log's minimum still duration
SPOT_M = STILL_SPEED * STILL_MIN_S  # how far a head counted as still can drift: 0.06 m


def load_head(folder: Path) -> Tuple[np.ndarray, np.ndarray]:
    t0 = json.loads((folder / "session.json").read_text())["startNs"]
    rows = [json.loads(l) for l in open(folder / "hmd.jsonl") if l.strip()]
    t = np.array([(r["t"] - t0) / 1e9 for r in rows])
    xz = np.array([r["pos"] for r in rows], dtype=float)[:, [0, 2]]
    return t, xz


def _smooth(x: np.ndarray, w: int) -> np.ndarray:
    if w <= 1:
        return x
    k = np.ones(w) / w
    pad = np.pad(x, ((w // 2, w - 1 - w // 2), (0, 0)), mode="edge")
    return np.stack([np.convolve(pad[:, c], k, mode="valid") for c in range(x.shape[1])], axis=1)


def _runs(mask: np.ndarray) -> List[Tuple[int, int]]:
    out, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            k = i
            while k + 1 < n and mask[k + 1]:
                k += 1
            out.append((i, k))
            i = k + 1
        else:
            i += 1
    return out


def walks(t: np.ndarray, xz: np.ndarray) -> List[dict]:
    if len(t) < 3:
        return []
    hz = (len(t) - 1) / max(1e-6, t[-1] - t[0])
    p = _smooth(xz, max(1, int(round(HEAD_SMOOTH_S * hz))))
    speed = np.linalg.norm(np.gradient(p, axis=0) / np.gradient(t)[:, None], axis=1)
    runs = _runs(speed > STILL_SPEED)
    merged: List[List[int]] = []
    for i, k in runs:
        if merged and t[i] - t[merged[-1][1]] < MERGE_GAP_S:
            merged[-1][1] = k
        else:
            merged.append([i, k])
    out = []
    for i, k in merged:
        disp = float(np.linalg.norm(p[k] - p[i]))
        if disp >= MIN_DISP_M:
            seg = p[i:k + 1]
            i = i + int(np.nonzero(np.linalg.norm(seg - seg[0], axis=1) <= SPOT_M)[0].max())
            seg = p[i:k + 1]
            k = i + int(np.nonzero(np.linalg.norm(seg - seg[-1], axis=1) <= SPOT_M)[0].min())
            out.append({"kind": "walk", "start": round(float(t[i]), 2), "end": round(float(t[k]), 2),
                        "distance_m": round(float(np.sum(np.linalg.norm(np.diff(p[i:k + 1], axis=0), axis=1))), 2),
                        "displacement_m": round(disp, 2), "peak_speed": round(float(speed[i:k + 1].max()), 2)})
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="procqc.signals.walk_v2")
    ap.add_argument("events")
    ap.add_argument("sensor_root")
    ap.add_argument("out")
    a = ap.parse_args(argv)
    root, n, missing = Path(a.sensor_root), 0, []
    with open(a.out, "w") as f:
        for l in open(a.events):
            if not l.strip():
                continue
            r = json.loads(l)
            d = root / r["session"]
            if not (d / "hmd.jsonl").exists():
                missing.append(r["session"])
                continue
            w = walks(*load_head(d))
            r["events"] = sorted([e for e in r["events"] if e["kind"] != "walk"] + w, key=lambda e: (e["start"], e["kind"]))
            r["counts"]["walk"] = len(w)
            r["walk_version"] = 2
            r.setdefault("settings", {}).update(walk_v2={"still_speed": STILL_SPEED, "merge_gap_s": MERGE_GAP_S,
                                                         "min_disp_m": MIN_DISP_M, "spot_m": SPOT_M,
                                                         "head_smooth_s": HEAD_SMOOTH_S})
            f.write(json.dumps(r) + "\n")
            n += 1
    print(json.dumps({"written": n, "missing_sensors": len(missing)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
