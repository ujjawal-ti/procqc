"""Sensor event log for headset recordings: gestures, bends, walking, standing still and grip candidates.

Input is one session folder written by the headset capture app:
  session.json        task title + SOP text, startNs, durationMs
  hmd.jsonl           {"t": ns, "pos": [x, y, z], "rot": [qx, qy, qz, qw]}            (head)
  hand-left.jsonl     {"t": ns, "state": "tracked" | "lost", "joints": 26 x [x, y, z, qx, qy, qz, qw]}
  hand-right.jsonl    same, OpenXR joint order (0 palm, 1 wrist, 2-5 thumb, 6-10 index, ..., 21-25 little)
Times in the log are seconds from session.startNs, which is the video's time base (checked to within 0.08 s).
Hand x/z share the head's frame; hand y carries a per-session offset, so only relative heights are used.

What each event means, and how far it can be trusted (checked on frames of the Meta pilot recordings):
  gesture  thumbs-up: four fingers curled, thumb extended and pointing up. Reliable (start 97/100, end 100/100).
  bend     the head drops below standing height: on floor tasks, one bend per pick-up or put-down. Reliable on
           floor tasks; table tasks have none. `hand` is the lower hand at the bottom of the bend and `place` groups
           bends at the same spot (a spot visited again and again is usually the destination).
  walk     horizontal head speed above a threshold.
  still    horizontal head speed below a threshold. Whether the SOP's "stand still" is met depends on this
           threshold; it is a setting, not a verdict.
  grip     the hand's fingers closed relative to its own open pose. NOT reliable on its own: fingertip holds of small
           objects are missed and relaxed fists while walking are reported. A candidate for the video to confirm.
No model calls.

Usage (from the repository root):
  python3 -m procqc.signals.sensors SESSION_DIR_OR_ROOT [...] [--out events.jsonl]
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

PALM, WRIST, THUMB_META, THUMB_TIP, MID_PROX = 0, 1, 2, 5, 12
TIPS = (5, 10, 15, 20, 25)  # thumb, index, middle, ring, little
HANDS = ("left", "right")


@dataclass
class SensorSettings:
    lost_gap_s: float = 0.5          # untracked stretches shorter than this are interpolated
    head_smooth_s: float = 0.3
    hand_smooth_s: float = 0.15
    bend_drop_m: float = 0.35        # head below its median height by this much
    bend_min_s: float = 0.3
    walk_speed: float = 0.35         # m/s, horizontal head speed
    walk_min_s: float = 0.5
    still_speed: float = 0.12        # m/s
    still_min_s: float = 0.5
    still_before_s: float = 4.0      # window before a bend searched for the longest standing-still stretch
    thumb_curl_max: float = 0.62     # four fingers' tip-to-palm distance / hand size
    thumb_ext_min: float = 0.95
    thumb_up_min: float = 0.35       # vertical component of the thumb's direction
    gesture_min_s: float = 0.25
    marker_window_s: float = 3.0     # a gesture this close to the start / end is the start / end marker
    grip_closure: float = 0.15
    grip_min_s: float = 0.8
    grip_open_pct: float = 90.0      # percentile of finger curl taken as the hand's open pose
    place_radius_m: float = 0.5


@dataclass
class Session:
    sid: str
    task: str
    sop: str
    duration_s: float
    t: np.ndarray                    # (n,) seconds from startNs
    head: np.ndarray                 # (n, 3)
    hands: Dict[str, Tuple[np.ndarray, np.ndarray]]  # side -> (tracked (n,), joints (n, 26, 3))

    @property
    def hz(self) -> float:
        return (len(self.t) - 1) / (self.t[-1] - self.t[0]) if len(self.t) > 1 and self.t[-1] > self.t[0] else 72.0


def _jsonl(path: Path) -> List[dict]:
    return [json.loads(line) for line in open(path) if line.strip()]


def load_session(folder) -> Session:
    folder = Path(folder)
    s = json.loads((folder / "session.json").read_text())
    t0 = s["startNs"]
    head = _jsonl(folder / "hmd.jsonl")
    raw = {side: _jsonl(folder / f"hand-{side}.jsonl") for side in HANDS}
    n = min([len(head)] + [len(r) for r in raw.values()])
    hands = {}
    for side, rows in raw.items():
        ok = np.array([r.get("state") == "tracked" for r in rows[:n]])
        j = np.array([r["joints"] for r in rows[:n]], dtype=float)[:, :, :3]
        hands[side] = (ok, j)
    task = s.get("task") or {}
    return Session(sid=folder.name, task=task.get("title", ""), sop=task.get("description", ""),
                   duration_s=s.get("durationMs", 0) / 1000, t=np.array([(h["t"] - t0) / 1e9 for h in head[:n]]),
                   head=np.array([h["pos"] for h in head[:n]], dtype=float), hands=hands)


# ---------- signal helpers (numpy only) ----------

def _win(seconds: float, hz: float) -> int:
    return max(1, int(round(seconds * hz)) | 1)


def _smooth(x: np.ndarray, w: int) -> np.ndarray:
    """Moving average along axis 0 with edge padding; NaNs stay NaN where the window has no data."""
    if w <= 1:
        return x.copy()
    pad = w // 2
    xp = np.pad(x, [(pad, pad)] + [(0, 0)] * (x.ndim - 1), mode="edge")
    k = np.ones(w) / w
    if x.ndim == 1:
        return np.convolve(xp, k, mode="valid")
    return np.stack([np.convolve(xp[:, i], k, mode="valid") for i in range(x.shape[1])], 1)


def _median(x: np.ndarray, w: int) -> np.ndarray:
    if w <= 1:
        return x.copy()
    pad = w // 2
    xp = np.pad(x, [(pad, pad)] + [(0, 0)] * (x.ndim - 1), mode="edge")
    v = np.lib.stride_tricks.sliding_window_view(xp, w, axis=0)
    return np.nanmedian(v, axis=-1)


def _majority(mask: np.ndarray, w: int) -> np.ndarray:
    return _smooth(mask.astype(float), w) > 0.5


def segments(mask: np.ndarray, t: np.ndarray, min_s: float = 0.0) -> List[Tuple[int, int]]:
    """Index ranges [i, k] (inclusive) of True runs lasting at least min_s."""
    out, i, n = [], 0, len(mask)
    while i < n:
        if not mask[i]:
            i += 1
            continue
        k = i
        while k + 1 < n and mask[k + 1]:
            k += 1
        if t[k] - t[i] >= min_s:
            out.append((i, k))
        i = k + 1
    return out


def _long_gaps(ok: np.ndarray, t: np.ndarray, min_s: float) -> np.ndarray:
    lost = np.zeros(len(ok), bool)
    for i, k in segments(~ok, t):
        if t[k] - t[i] + (t[1] - t[0] if len(t) > 1 else 0) > min_s:
            lost[i:k + 1] = True
    return lost


def _fill(x: np.ndarray, ok: np.ndarray) -> np.ndarray:
    x = x.astype(float).copy()
    if ok.sum() < 2:
        return np.full_like(x, np.nan)
    idx = np.arange(len(x))
    flat = x.reshape(len(x), -1)
    for c in range(flat.shape[1]):
        flat[~ok, c] = np.interp(idx[~ok], idx[ok], flat[ok, c])
    return flat.reshape(x.shape)


def _r(v, nd=2):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), nd)


# ---------- features ----------

def features(s: Session, cfg: SensorSettings) -> dict:
    hz, t = s.hz, s.t
    head = _smooth(s.head, _win(cfg.head_smooth_s, hz))
    dt = np.gradient(t) if len(t) > 1 else np.ones(1)
    vel = np.gradient(head, axis=0) / dt[:, None]
    f = {"t": t, "head_y": head[:, 1], "head_drop": np.median(head[:, 1]) - head[:, 1],
         "head_speed": np.linalg.norm(vel[:, [0, 2]], axis=1), "head_xz": head[:, [0, 2]]}
    for side in HANDS:
        ok, j = s.hands[side]
        lost = _long_gaps(ok, t, cfg.lost_gap_s)
        jf = _fill(j, ok)
        jf = _median(jf, _win(cfg.hand_smooth_s, hz)) if np.isfinite(jf).all() else jf
        jf[lost] = np.nan
        size = np.maximum(np.linalg.norm(jf[:, MID_PROX] - jf[:, WRIST], axis=1), 1e-3)
        tips = np.stack([np.linalg.norm(jf[:, k] - jf[:, PALM], axis=1) / size for k in TIPS], 1)
        thumb = jf[:, THUMB_TIP] - jf[:, THUMB_META]
        thumb_up = thumb[:, 1] / np.maximum(np.linalg.norm(thumb, axis=1), 1e-6)
        palm = jf[:, PALM]
        pv = np.gradient(_smooth(np.nan_to_num(palm), _win(cfg.hand_smooth_s, hz)), axis=0) / dt[:, None]
        speed = np.linalg.norm(pv, axis=1)
        speed[lost] = np.nan
        f[side] = {"tracked": ok & ~lost, "lost": lost, "tips": tips, "thumb_up": thumb_up, "palm": palm, "speed": speed}
    return f


# ---------- events ----------

def _gestures(f: dict, cfg: SensorSettings, hz: float, dur: float) -> List[dict]:
    t = f["t"]
    per_hand = []
    for side in HANDS:
        h = f[side]
        tips = h["tips"]
        with np.errstate(invalid="ignore"):
            m = h["tracked"] & (np.nanmax(tips[:, 1:], 1) < cfg.thumb_curl_max) & (tips[:, 0] > cfg.thumb_ext_min) & \
                (h["thumb_up"] > cfg.thumb_up_min)
        m = _majority(m, _win(0.3, hz))
        per_hand += [(t[i], t[k], side) for i, k in segments(m, t, cfg.gesture_min_s)]
    per_hand.sort()
    merged: List[dict] = []
    for a, b, side in per_hand:  # overlapping left/right thumbs-ups are one gesture
        if merged and a <= merged[-1]["end"] + 0.3:
            g = merged[-1]
            g["end"] = max(g["end"], b)
            if side not in g["hands"]:
                g["hands"].append(side)
        else:
            merged.append({"kind": "gesture", "gesture": "thumbs_up", "start": a, "end": b, "hands": [side]})
    for g in merged:
        g["start"], g["end"] = _r(g["start"]), _r(g["end"])
        g["hands"].sort()
        g["role"] = "start_marker" if g["start"] <= cfg.marker_window_s else (
            "end_marker" if g["end"] >= dur - cfg.marker_window_s else "between")
    return merged


def _longest_run(mask: np.ndarray, hz: float) -> float:
    best = run = 0
    for v in mask:
        run = run + 1 if v else 0
        best = max(best, run)
    return best / hz


def _bends(f: dict, cfg: SensorSettings, hz: float) -> List[dict]:
    t = f["t"]
    out = []
    still = f["head_speed"] < cfg.still_speed
    for i, k in segments(f["head_drop"] > cfg.bend_drop_m, t, cfg.bend_min_s):
        b = i + int(np.argmax(f["head_drop"][i:k + 1]))
        # the acting hand is the one that reaches lowest during the bend (a hand can be untracked at the very bottom)
        lows = {}
        for side in HANDS:
            y = f[side]["palm"][i:k + 1, 1]
            if np.isfinite(y).any():
                lows[side] = i + int(np.nanargmin(y))
        hand = min(lows, key=lambda sd: f[sd]["palm"][lows[sd], 1]) if lows else None
        pos = f[hand]["palm"][lows[hand]] if hand else None
        lo = int(np.searchsorted(t, t[i] - cfg.still_before_s))
        out.append({"kind": "bend", "start": _r(t[i]), "end": _r(t[k]), "bottom": _r(t[b]),
                    "head_drop_m": _r(f["head_drop"][b]), "hand": hand,
                    "hand_pos": [_r(v) for v in pos] if pos is not None else None,
                    "hand_lost_in_bend": [sd for sd in HANDS if f[sd]["lost"][i:k + 1].any()],
                    "still_before_s": _r(_longest_run(still[lo:i], hz))})
    return out


def _places(bends: List[dict], radius: float) -> List[dict]:
    """Group bends whose acting hand was at the same floor spot (x/z), greedy in time order."""
    places: List[dict] = []
    for idx, b in enumerate(bends):
        if not b["hand_pos"]:
            b["place"] = None
            continue
        p = np.array([b["hand_pos"][0], b["hand_pos"][2]])
        best = min(places, key=lambda q: np.linalg.norm(q["_c"] - p), default=None)
        if best is not None and np.linalg.norm(best["_c"] - p) <= radius:
            best["_pts"].append(p)
            best["_c"] = np.mean(best["_pts"], 0)
            best["bends"].append(idx)
        else:
            best = {"id": len(places), "_pts": [p], "_c": p, "bends": [idx]}
            places.append(best)
        b["place"] = best["id"]
    return [{"id": q["id"], "pos_xz": [_r(v) for v in q["_c"]], "visits": len(q["bends"]),
             "times": [bends[i]["bottom"] for i in q["bends"]]} for q in places]


def _grips(f: dict, cfg: SensorSettings, hz: float, gestures: List[dict]) -> List[dict]:
    t = f["t"]
    out = []
    for side in HANDS:
        h = f[side]
        curl = np.where(h["tracked"], np.nanmean(h["tips"][:, 1:], 1), np.nan)
        if not np.isfinite(curl).any():
            continue
        closure = 1 - curl / np.nanpercentile(curl, cfg.grip_open_pct)
        busy = np.zeros(len(t), bool)
        for g in gestures:  # closing the hand for a thumbs-up is not a grip
            busy |= (t >= g["start"] - 0.4) & (t <= g["end"] + 0.4)
        with np.errstate(invalid="ignore"):
            m = h["tracked"] & (closure > cfg.grip_closure)
        m = _majority(m, _win(0.4, hz))
        for i, k in segments(m, t, cfg.grip_min_s):
            if busy[i] or busy[k]:
                continue
            out.append({"kind": "grip", "hand": side, "start": _r(t[i]), "end": _r(t[k]),
                        "closure": _r(np.nanmedian(closure[i:k + 1])), "reliability": "low",
                        "start_pos": [_r(v) for v in h["palm"][i]], "end_pos": [_r(v) for v in h["palm"][k]]})
    return out


def event_log(s: Session, cfg: Optional[SensorSettings] = None) -> dict:
    cfg = cfg or SensorSettings()
    with warnings.catch_warnings():  # untracked stretches are NaN by design
        warnings.simplefilter("ignore", RuntimeWarning)
        return _event_log(s, cfg)


def _event_log(s: Session, cfg: SensorSettings) -> dict:
    hz = s.hz
    f = features(s, cfg)
    t = f["t"]
    dur = s.duration_s or float(t[-1])
    gestures = _gestures(f, cfg, hz, dur)
    bends = _bends(f, cfg, hz)
    places = _places(bends, cfg.place_radius_m)
    walks = []
    for i, k in segments(f["head_speed"] > cfg.walk_speed, t, cfg.walk_min_s):
        walks.append({"kind": "walk", "start": _r(t[i]), "end": _r(t[k]),
                      "distance_m": _r(np.sum(np.linalg.norm(np.diff(f["head_xz"][i:k + 1], axis=0), axis=1)))})
    stills = [{"kind": "still", "start": _r(t[i]), "end": _r(t[k])}
              for i, k in segments(f["head_speed"] < cfg.still_speed, t, cfg.still_min_s)]
    grips = _grips(f, cfg, hz, gestures)
    events = sorted(gestures + bends + walks + stills + grips, key=lambda e: (e["start"], e["kind"]))
    tracking = {side: {"tracked_fraction": _r(f[side]["tracked"].mean(), 3),
                       "lost": [[_r(t[i]), _r(t[k])] for i, k in segments(f[side]["lost"], t)]} for side in HANDS}
    markers = {"start": next((g for g in gestures if g["role"] == "start_marker"), None),
               "end": next((g for g in reversed(gestures) if g["role"] == "end_marker"), None)}
    return {"session": s.sid, "task": s.task, "duration_s": _r(dur), "sample_hz": _r(hz, 1),
            "time_base": "seconds from session.startNs (= video time)", "markers": markers,
            "counts": {k: sum(e["kind"] == k for e in events) for k in ("gesture", "bend", "walk", "still", "grip")},
            "places": places, "tracking": tracking, "events": events, "settings": asdict(cfg)}


def _session_dirs(paths: Sequence[str]) -> List[Path]:
    out = []
    for p in map(Path, paths):
        if (p / "session.json").exists():
            out.append(p)
        else:
            out += sorted(d for d in p.iterdir() if (d / "session.json").exists())
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="procqc.signals.sensors", description=__doc__.split("\n\n")[0])
    ap.add_argument("paths", nargs="+", help="session folders, or folders that contain them")
    ap.add_argument("--out", help="write one JSON line per session here (default: print a summary only)")
    a = ap.parse_args(argv)
    dirs = _session_dirs(a.paths)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    fh = open(a.out, "w") if a.out else None
    for d in dirs:
        try:
            log = event_log(load_session(d))
        except Exception as e:  # one broken session must not stop a batch
            print(f"{d.name}: error {e!r}", file=sys.stderr)
            continue
        if fh:
            fh.write(json.dumps(log) + "\n")
        m, c = log["markers"], log["counts"]
        top = max(log["places"], key=lambda q: q["visits"], default=None)
        start = "%.1f" % m["start"]["start"] if m["start"] else "-"
        end = "%.1f" % m["end"]["end"] if m["end"] else "-"
        print(f"{d.name[:8]}  {log['task'][:40]:40s} {log['duration_s']:6.1f}s  start {start:>5}  end {end:>5}  "
              f"bends {c['bend']:2d}  most-visited place {top['visits'] if top else 0}  grips {c['grip']:2d}")
    if fh:
        fh.close()
    print(f"{len(dirs)} sessions" + (f" -> {a.out}" if a.out else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
