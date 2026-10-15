"""Select and download internal clips (video + headset sensor files) from the FTS S3 bucket (S3_BUCKET in procqc/.env).

Each clip lives in one S3 folder, the folder of its `video_path` in AutoQC (AUTOQC_TASKS_TABLE):
  project/<p>/workflow/<w>/job/<parent job>/clip/Clip-N/
with the video next to the sensor files (session.json, hmd.jsonl, hand-left/right.jsonl, controller-left/right.jsonl).
Every video in the folder is the side-by-side stereo recording (2880x1080): original_video.mp4, video.mp4 (same file)
and *_backup_* copies. Only --video-name is downloaded; the other videos are skipped.
Downloads keep the Meta_Pilot layout, so the existing tools run on them unchanged:
  VIDEO_DIR/<child_job_id>.mp4          the left eye (1440x1080) cut from the stereo video with ffmpeg, as in
                                        Meta_Pilot (checked on 04c9a531: same frame count, mean pixel difference 2.5
                                        against the left half, 25-41 against the right); --eye right|both to change
  SENSOR_DIR/<child_job_id>/<file>      every other file in the folder, minus --exclude

Credentials: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY and AWS_SESSION_TOKEN (optional AWS_REGION) from procqc/.env,
read with dotenv_values and never printed; without them, or with --profile, the standard AWS chain is used. No
signed links are made. Only objects under the given clips' folders are read. Sensor files already present with the same
size, and videos already present, are skipped, so an interrupted download can be resumed (each file is written to a
temporary name and renamed when complete).

Usage (from the repository root):
  # pick clips from fts_ground_truth search output, matched to our SOPs (by the Objects: and To: lines)
  python3 -m procqc.internal.s3_fetch select boundary_cases.csv SOP_DIR OUT.csv --batch BATCH_PREFIX \\
      --take recording_end=discard:13 recording_end=medium:30 recording_start=discard:25 recording_start=medium:15
  # what would be downloaded, with sizes (no download)
  python3 -m procqc.internal.s3_fetch list CLIPS.csv [--profile NAME] [--limit N]
  # download
  python3 -m procqc.internal.s3_fetch get CLIPS.csv VIDEO_DIR SENSOR_DIR [--eye left|right|both] [--keep-stereo DIR]
      [--profile NAME] [--workers 4]
CLIPS.csv needs child_job_id and video_path columns.
"""
from __future__ import annotations

import argparse
import csv
import fnmatch
import random
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from procqc.internal import ENV, setting

VIDEO_NAME = "original_video.mp4"
EXCLUDE = ["*.json.tmp"]
EYE_CROP = {"left": "crop=iw/2:ih:0:0", "right": "crop=iw/2:ih:iw/2:0", "both": None}


def cut_eye(stereo: Path, dest: Path, eye: str) -> None:
    """One eye of the side-by-side video as H.264 (near-lossless, audio kept if present); "both" keeps the file."""
    if EYE_CROP[eye] is None:
        stereo.replace(dest)
        return
    tmp = dest.with_name(dest.stem + ".cut.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(stereo), "-map", "0:v:0", "-map", "0:a?",
                    "-vf", EYE_CROP[eye], "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-c:a", "copy", "-movflags", "+faststart", str(tmp)], check=True)
    tmp.replace(dest)


def _client(profile: Optional[str], accelerate: bool):
    import boto3
    from botocore.config import Config
    if profile:
        session = boto3.Session(profile_name=profile)
    else:
        from dotenv import dotenv_values
        e = dotenv_values(ENV) if ENV.exists() else {}
        keys = {"aws_access_key_id": e.get("AWS_ACCESS_KEY_ID"), "aws_secret_access_key": e.get("AWS_SECRET_ACCESS_KEY"),
                "aws_session_token": e.get("AWS_SESSION_TOKEN") or None,
                "region_name": e.get("AWS_REGION") or e.get("AWS_DEFAULT_REGION") or None}
        session = boto3.Session(**keys) if keys["aws_access_key_id"] else boto3.Session()
    return session.client("s3", config=Config(s3={"use_accelerate_endpoint": accelerate},
                                              retries={"max_attempts": 8, "mode": "adaptive"}))


def _prefix(video_path: str) -> str:
    return video_path.rsplit("/", 1)[0].strip("/") + "/"


def _read_clips(path: str) -> List[dict]:
    rows = [r for r in csv.DictReader(open(path)) if r.get("child_job_id", "").strip()]
    missing = [r["child_job_id"] for r in rows if not r.get("video_path", "").strip()]
    if missing:
        print(f"skipping {len(missing)} clips with no video_path, e.g. {missing[0]}")
    return [r for r in rows if r.get("video_path", "").strip()]


def list_clip(s3, video_path: str) -> List[dict]:
    out, token = [], None
    while True:
        kw = {"Bucket": setting("S3_BUCKET"), "Prefix": _prefix(video_path)}
        if token:
            kw["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kw)
        out += [{"key": o["Key"], "size": o["Size"]} for o in resp.get("Contents", [])]
        if not resp.get("IsTruncated"):
            return out
        token = resp["NextContinuationToken"]


def plan(objs: List[dict], cid: str, video_dir: Path, sensor_dir: Path, video_name: str,
         exclude: Sequence[str]) -> List[tuple]:
    """(key, size, local path) for one clip; only files directly in the clip folder."""
    jobs = []
    for o in objs:
        name = o["key"].rsplit("/", 1)[-1]
        if not name:
            continue
        if name == video_name:
            jobs.append((o["key"], o["size"], video_dir / f"{cid}.mp4"))
        elif not any(fnmatch.fnmatch(name, pat) for pat in exclude) and not name.endswith(".mp4"):
            jobs.append((o["key"], o["size"], sensor_dir / cid / name))
    return jobs


def _fmt(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def cmd_select(a) -> int:
    rows = list(csv.DictReader(open(a.cases)))
    from procqc.internal.fts_ground_truth import _sop_line
    # Objects and To together: tasks can share a destination (cups and dishware both go to the sink)
    key_task: Dict[tuple, str] = {}
    for p in Path(a.sop_dir).glob("*.txt"):
        t = p.read_text()
        key_task[(_sop_line(t, "Objects"), _sop_line(t, "To"))] = p.stem
    if a.batch:
        rows = [r for r in rows if r.get("batch_id", "").startswith(a.batch)]
    for r in rows:
        r["task_id"] = key_task.get((r.get("objects", "").strip(), r.get("to", "").strip()), "")
    rows = [r for r in rows if r["task_id"] and r.get("video_path")]
    rng = random.Random(a.seed)
    chosen: Dict[str, dict] = {}
    for spec in a.take:
        cond, n = spec.rsplit(":", 1)
        attr, val = cond.split("=", 1)
        pool = [r for r in rows if r.get(attr) == val and r["child_job_id"] not in chosen]
        rng.shuffle(pool)
        for r in pool[:int(n)]:
            chosen[r["child_job_id"]] = dict(r, selected_for=cond)
        print(f"{cond}: {min(int(n), len(pool))} of {len(pool)} available")
    out = list(chosen.values())
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print(f"wrote {len(out)} clips to {a.out}")
    return 0


def cmd_list(a) -> int:
    s3 = _client(a.profile, a.accelerate)
    clips = _read_clips(a.clips)[: a.limit or None]
    total, names = 0, {}
    for r in clips:
        objs = list_clip(s3, r["video_path"])
        for o in objs:
            name = o["key"].rsplit("/", 1)[-1]
            names.setdefault(name, []).append(o["size"])
        jobs = plan(objs, r["child_job_id"], Path("V"), Path("S"), a.video_name, a.exclude)
        total += sum(j[1] for j in jobs)
        if not any(j[2].parent == Path("V") for j in jobs):
            print(f"  {r['child_job_id']}: no {a.video_name} in {_prefix(r['video_path'])}")
    print(f"{len(clips)} clips; files seen in the clip folders (count, median size):")
    for name, sizes in sorted(names.items()):
        print(f"  {name:28s} {len(sizes):4d}  {_fmt(sorted(sizes)[len(sizes) // 2])}")
    print(f"would download {_fmt(total)} (video = {a.video_name}; excluded: {', '.join(a.exclude)})")
    return 0


def cmd_get(a) -> int:
    s3 = _client(a.profile, a.accelerate)
    clips = _read_clips(a.clips)
    video_dir, sensor_dir = Path(a.video_dir), Path(a.sensor_dir)
    jobs = []
    for r in clips:
        jobs += plan(list_clip(s3, r["video_path"]), r["child_job_id"], video_dir, sensor_dir, a.video_name, a.exclude)
    def done(job):
        dest = job[2]
        if dest.parent == video_dir:  # the cut video differs in size from the stereo source
            return dest.exists()
        return dest.exists() and dest.stat().st_size == job[1]

    todo = [j for j in jobs if not done(j)]
    print(f"{len(clips)} clips, {len(jobs)} files, {_fmt(sum(j[1] for j in jobs))}; "
          f"{len(jobs) - len(todo)} already present, downloading {len(todo)} ({_fmt(sum(j[1] for j in todo))})")

    def one(job):
        key, size, dest = job
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".part")
        s3.download_file(setting("S3_BUCKET"), key, str(tmp))
        if dest.parent != video_dir:
            tmp.rename(dest)
            return dest
        stereo = tmp.with_name(dest.stem + ".stereo.mp4")
        tmp.rename(stereo)
        if a.keep_stereo:
            keep = Path(a.keep_stereo) / f"{dest.stem}.mp4"
            keep.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["cp", str(stereo), str(keep)], check=True)
        cut_eye(stereo, dest, a.eye)
        stereo.unlink(missing_ok=True)
        return dest

    failed = []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(one, j): j for j in todo}
        for i, f in enumerate(futs, 1):
            try:
                f.result()
            except Exception as exc:  # noqa: BLE001 - report and continue; a rerun resumes
                failed.append((futs[f][0], type(exc).__name__))
            if i % 50 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)} done, {len(failed)} failed")
    for key, err in failed[:10]:
        print(f"  failed: {key.rsplit('/', 3)[-3:]} {err}")
    missing_video = [r["child_job_id"] for r in clips if not (video_dir / f"{r['child_job_id']}.mp4").exists()]
    print(f"videos present for {len(clips) - len(missing_video)}/{len(clips)} clips")
    return 1 if failed else 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="procqc.internal.s3_fetch")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("select")
    s.add_argument("cases")
    s.add_argument("sop_dir")
    s.add_argument("out")
    s.add_argument("--batch", default=None, help="batch_id prefix")
    s.add_argument("--take", nargs="+", required=True, help="ATTR=VALUE:N, taken in order without repeats")
    s.add_argument("--seed", type=int, default=0)
    for name in ("list", "get"):
        p = sub.add_parser(name)
        p.add_argument("clips")
        if name == "get":
            p.add_argument("video_dir")
            p.add_argument("sensor_dir")
            p.add_argument("--workers", type=int, default=4)
            p.add_argument("--eye", choices=sorted(EYE_CROP), default="left")
            p.add_argument("--keep-stereo", default=None, help="also keep the stereo video in this directory")
        else:
            p.add_argument("--limit", type=int, default=0)
        p.add_argument("--profile", default=None)
        p.add_argument("--video-name", default=VIDEO_NAME)
        p.add_argument("--exclude", nargs="*", default=EXCLUDE)
        p.add_argument("--no-accelerate", dest="accelerate", action="store_false",
                       help="the stored URLs use the accelerate endpoint; turn it off if the bucket refuses it")
    a = ap.parse_args(argv)
    return {"select": cmd_select, "list": cmd_list, "get": cmd_get}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
