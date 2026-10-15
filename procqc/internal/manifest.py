"""Manifest for internal headset recordings: one JSON row per recording, read by the headset checks.

Each recording is a video named <session>.mp4 and a sensor folder <session>/ holding session.json (the task title
and the SOP text the operator saw) and the sensor streams. The task id is the title in lower case with every run of
other characters replaced by "_"; its SOP and graph are <task_id>.txt and <task_id>.yaml.

    sops      write each task's SOP verbatim from session.json ("Name: <title>", then "Description:" and the text)
    build     write the manifest rows

The end marker (the declared-done thumbs up) comes from the standard sensor event log (procqc.signals.sensors);
without it, rows carry "end_marker": null and the checks fall back to the end of the video.

    python3 -m procqc.internal.manifest sops SENSOR_DIR SOP_DIR
    python3 -m procqc.internal.manifest build VIDEO_DIR SENSOR_DIR SOP_DIR GRAPH_DIR OUT [--events EVENTS]

Row: {session, task_id, task, video, duration_s, end_marker {start, end} | null, graph, sop}.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence


def task_id(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")


def sop_text(task: dict) -> str:
    return f"Name: {task['title']}\n\nDescription:\n{task.get('instructions') or task.get('description') or ''}\n"


def sessions(sensor_dir: Path) -> List[dict]:
    out = []
    for p in sorted(sensor_dir.glob("*/session.json")):
        s = json.loads(p.read_text())
        out.append({"session": p.parent.name, "task": s["task"], "duration_s": round(s.get("durationMs", 0) / 1000, 2)})
    return out


def end_markers(events: Optional[str]) -> Dict[str, Optional[dict]]:
    if not events:
        return {}
    res = {}
    for line in open(events):
        if line.strip():
            e = json.loads(line)
            m = (e.get("markers") or {}).get("end")
            res[e["session"]] = {"start": m["start"], "end": m["end"]} if m else None
    return res


def write_sops(sensor_dir: Path, sop_dir: Path) -> int:
    sop_dir.mkdir(parents=True, exist_ok=True)
    seen: Dict[str, str] = {}
    for s in sessions(sensor_dir):
        tid, text = task_id(s["task"]["title"]), sop_text(s["task"])
        if tid in seen and seen[tid] != text:
            print(f"warning: {tid}: SOP text differs between recordings; keeping the first")
            continue
        seen[tid] = text
    for tid, text in seen.items():
        (sop_dir / f"{tid}.txt").write_text(text)
    print(f"{len(seen)} SOPs -> {sop_dir}")
    return 0


def build(video_dir: Path, sensor_dir: Path, sop_dir: Path, graph_dir: Path, out: Path, events: Optional[str]) -> int:
    ends = end_markers(events)
    rows, skipped = [], []
    for s in sessions(sensor_dir):
        tid = task_id(s["task"]["title"])
        video, sop, graph = video_dir / f"{s['session']}.mp4", sop_dir / f"{tid}.txt", graph_dir / f"{tid}.yaml"
        missing = [str(p) for p in (video, sop, graph) if not p.exists()]
        if missing:
            skipped.append((s["session"], missing))
            continue
        rows.append({"session": s["session"], "task_id": tid, "task": s["task"]["title"], "video": str(video),
                     "duration_s": s["duration_s"], "end_marker": ends.get(s["session"]),
                     "graph": str(graph), "sop": str(sop)})
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"{len(rows)} rows -> {out}; skipped {len(skipped)}")
    for sid, miss in skipped[:10]:
        print(f"  {sid}: missing {', '.join(miss)}")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="procqc.internal.manifest")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sops")
    s.add_argument("sensor_dir")
    s.add_argument("sop_dir")
    b = sub.add_parser("build")
    for k in ("video_dir", "sensor_dir", "sop_dir", "graph_dir", "out"):
        b.add_argument(k)
    b.add_argument("--events", help="standard sensor event log (JSONL) with the end markers")
    a = ap.parse_args(argv)
    if a.cmd == "sops":
        return write_sops(Path(a.sensor_dir), Path(a.sop_dir))
    return build(Path(a.video_dir), Path(a.sensor_dir), Path(a.sop_dir), Path(a.graph_dir), Path(a.out), a.events)


if __name__ == "__main__":
    raise SystemExit(main())
