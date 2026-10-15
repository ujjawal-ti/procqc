"""Human-review ground truth for the internal Meta_Pilot clips, fetched from FTS (and the production AutoQC
verdicts from DataQC), following the team's FTS exploration notebook.

The FTS child job id is the clip id (the video file name). For each clip it keeps every completed review
submission on the review workflow (FTS_WORKFLOW_ID; Reviewer 1 / Reviewer 2 / Reviewer) with its ACCEPT / REJECT
decision and its rubric (one value per attribute: perfect / medium / discard). Queries are read-only and
filtered to the given clip ids.

Ground truth per clip (latest submission per reviewer step; the final decision is the last reviewer step):
  human_rejected   final decision is REJECT
  human_task_flag  task_specific_requirements (the rubric attribute for task completion) is medium or discard
  human_flagged    either of the two
  reasons          rubric attributes scored medium or discard, with the decision's own text fields if any

Credentials: FTS_* and DATAQC_* in procqc/.env (never printed). The workflow id and the table names are settings
there too: FTS_WORKFLOW_ID, FTS_SCHEMA (default public), AUTOQC_TASKS_TABLE, DATAQC_RECORDS_TABLE.

Search mode: every job on the workflow whose final review scores any of the given rubric parameters medium or
discard (default recording_start, recording_end), with the job's video location from AutoQC
(AUTOQC_TASKS_TABLE; the query string of the stored URL, which can carry a signature, is dropped).

Usage (from the repository root):
  python3 -m procqc.internal.fts_ground_truth CLIP_IDS.csv OUT_DIR [--ours RUN_DIR] [--verdicts verdicts.jsonl]
  python3 -m procqc.internal.fts_ground_truth search OUT_DIR [--attrs recording_start recording_end]
CLIP_IDS.csv needs a clip_id column (test_clip_ids.csv format).
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from procqc.internal import ENV, setting, sql_name

STEP_ORDER = {"Reviewer": 0, "Reviewer 1": 1, "Reviewer 2": 2}
TASK_ATTR = "task_specific_requirements"
# rubric parameters closest to our checks (Snowbird Quality Rubric): recording_end discard = "ends before the
# task is complete" (early termination); object_handling = "move objects directly to where they belong"
# (wrong destination); scene_state = setup realism (setup errors)
KEY_ATTRS = ["recording_end", TASK_ATTR, "object_handling", "scene_state"]

FTS_SQL = """
WITH reviews AS (
  SELECT te.job_id::text AS child_job_id, te.task_id::text AS review_task_id, s.name AS reviewer_step,
         ts.updated_at AS submitted_at, ts.current_output_container_id AS container_id,
         ROW_NUMBER() OVER (PARTITION BY te.task_id, s.name ORDER BY ts.updated_at DESC) AS submission_rank
  FROM {fts}.task_extensions te
  JOIN {fts}.jobs j              ON j.id = te.job_id
  JOIN {fts}.steps s             ON s.id = te.step_id
  JOIN {fts}.task_assignments ta ON ta.task_id = te.task_id
  JOIN {fts}.task_submissions ts ON ts.assignment_id = ta.id
  WHERE j.workflow_id = %(workflow)s
    AND te.job_id = ANY(%(ids)s::uuid[])
    AND s.name IN ('Reviewer 1', 'Reviewer 2', 'Reviewer')
    AND ta.status = 'COMPLETE' AND ts.status = 'COMPLETE'
)
SELECT r.child_job_id, r.review_task_id, r.reviewer_step, r.submitted_at, r.submission_rank,
       c.decision->>'status' AS decision_status, c.decision AS decision_json,
       vv.data->'value'->'review_result'->'value'->'rubric' AS rubric
FROM reviews r
JOIN {fts}.containers c ON c.id = r.container_id
LEFT JOIN {fts}.value_versions vv ON vv.id = COALESCE(
    c.data->'data'->'response'->'main_info'->>'value_version_id',
    c.data->'data'->'main_info'->>'value_version_id',
    c.data->'response'->'main_info'->>'value_version_id')::uuid
WHERE c.decision->>'status' IN ('ACCEPT', 'REJECT')
"""

SEARCH_SQL = """
WITH reviews AS (
  SELECT te.job_id::text AS child_job_id, s.name AS reviewer_step, ts.updated_at AS submitted_at,
         ts.current_output_container_id AS container_id,
         ROW_NUMBER() OVER (PARTITION BY te.task_id, s.name ORDER BY ts.updated_at DESC) AS submission_rank
  FROM {fts}.task_extensions te
  JOIN {fts}.jobs j              ON j.id = te.job_id
  JOIN {fts}.steps s             ON s.id = te.step_id
  JOIN {fts}.task_assignments ta ON ta.task_id = te.task_id
  JOIN {fts}.task_submissions ts ON ts.assignment_id = ta.id
  WHERE j.workflow_id = %(workflow)s
    AND s.name IN ('Reviewer 1', 'Reviewer 2', 'Reviewer')
    AND ta.status = 'COMPLETE' AND ts.status = 'COMPLETE'
)
SELECT r.child_job_id, r.reviewer_step, r.submitted_at, c.decision->>'status' AS decision_status,
       vv.data->'value'->'review_result'->'value'->'rubric' AS rubric
FROM reviews r
JOIN {fts}.containers c ON c.id = r.container_id
LEFT JOIN {fts}.value_versions vv ON vv.id = COALESCE(
    c.data->'data'->'response'->'main_info'->>'value_version_id',
    c.data->'data'->'main_info'->>'value_version_id',
    c.data->'response'->'main_info'->>'value_version_id')::uuid
WHERE r.submission_rank = 1 AND c.decision->>'status' IN ('ACCEPT', 'REJECT')
"""

AUTOQC_SQL = """
SELECT DISTINCT ON (fts_job_id) fts_job_id AS child_job_id, clip_id, batch_id, video_path,
       split_part(video_url, '?', 1) AS video_url, task_description
FROM {autoqc} WHERE fts_job_id = ANY(%(ids)s) ORDER BY fts_job_id, updated_at DESC
"""

DATAQC_SQL = "SELECT * FROM {dataqc} WHERE clip_id::text = ANY(%(ids)s)"


def _connect(prefix: str):
    import psycopg
    from dotenv import dotenv_values
    e = dotenv_values(ENV)
    return psycopg.connect(host=e[f"{prefix}_HOST"], port=e.get(f"{prefix}_PORT") or 5432, user=e[f"{prefix}_USER"],
                           password=e[f"{prefix}_PASS"], dbname=e[f"{prefix}_DATABASE"], connect_timeout=20)


def _rows(conn, sql: str, params: dict) -> List[dict]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def fetch(ids: Sequence[str]) -> tuple:
    with _connect("FTS") as conn:
        fts = _rows(conn, FTS_SQL.format(fts=sql_name("FTS_SCHEMA", "public")),
                    {"workflow": setting("FTS_WORKFLOW_ID"), "ids": list(ids)})
    try:
        with _connect("DATAQC") as conn:
            dq = _rows(conn, DATAQC_SQL.format(dataqc=sql_name("DATAQC_RECORDS_TABLE")), {"ids": list(ids)})
    except Exception as exc:  # noqa: BLE001 - the production AutoQC verdicts are optional context
        print(f"DataQC not fetched: {type(exc).__name__}")
        dq = []
    return fts, dq


def _text_fields(d, prefix="") -> Dict[str, str]:
    """Free-text fields anywhere in the decision JSON (reason / comment / note / feedback ...)."""
    out: Dict[str, str] = {}
    if isinstance(d, dict):
        for k, v in d.items():
            key = f"{prefix}{k}"
            if isinstance(v, (dict, list)):
                out.update(_text_fields(v, key + "."))
            elif isinstance(v, str) and k != "status" and any(w in k.lower() for w in
                                                              ("reason", "comment", "note", "feedback", "message")):
                if v.strip():
                    out[key] = v.strip()
    elif isinstance(d, list):
        for i, v in enumerate(d):
            out.update(_text_fields(v, f"{prefix}{i}."))
    return out


def _dataqc_task_completion(rec) -> dict:
    r = rec.get("record") if isinstance(rec.get("record"), dict) else {}
    for c in r.get("checks", []) or []:
        if isinstance(c, dict) and c.get("check_id") == "task_completion":
            ev = c.get("evidence")
            return {"autoqc_task_completion": c.get("verdict"),
                    "autoqc_task_completion_detail": (ev.get("detail", "") if isinstance(ev, dict) else str(ev or ""))[:400]}
    return {"autoqc_task_completion": None, "autoqc_task_completion_detail": ""}


def build(ids: Sequence[str], fts: List[dict], dq: List[dict], ours: Dict[str, dict], verdicts: Dict[str, dict],
          sop_task: Dict[str, str]) -> List[dict]:
    latest: Dict[str, Dict[str, dict]] = defaultdict(dict)
    n_subs: Dict[str, int] = defaultdict(int)
    for r in fts:
        n_subs[r["child_job_id"]] += 1
        if r["submission_rank"] == 1:
            latest[r["child_job_id"]][r["reviewer_step"]] = r
    dqi = {str(r.get("clip_id")): r for r in dq}
    out = []
    for cid in ids:
        steps = latest.get(cid, {})
        order = sorted(steps, key=lambda s: STEP_ORDER.get(s, 9))
        final = steps[order[-1]] if order else None
        row = {"clip_id": cid, "sop_task": sop_task.get(cid, ""), "in_fts": bool(order),
               "n_submissions": n_subs.get(cid, 0), "reviewer_steps": ";".join(order)}
        for s in ("Reviewer 1", "Reviewer 2"):
            r = steps.get(s)
            rub = r["rubric"] if r and isinstance(r["rubric"], dict) else {}
            k = s.replace("Reviewer ", "r")
            row[f"{k}_decision"] = r["decision_status"] if r else ""
            row[f"{k}_{TASK_ATTR}"] = rub.get(TASK_ATTR, "") if r else ""
        rub = final["rubric"] if final and isinstance(final["rubric"], dict) else {}
        row["final_step"] = order[-1] if order else ""
        row["final_decision"] = final["decision_status"] if final else ""
        row[f"final_{TASK_ATTR}"] = rub.get(TASK_ATTR, "")
        row["human_rejected"] = row["final_decision"] == "REJECT"
        row["human_task_flag"] = row[f"final_{TASK_ATTR}"] in ("medium", "discard")
        row["human_flagged"] = row["human_rejected"] or row["human_task_flag"]
        bad = sorted(f"{a}={v}" for a, v in rub.items() if v in ("medium", "discard"))
        texts = _text_fields(final["decision_json"]) if final else {}
        row["reasons"] = "; ".join(bad + [f"{k}: {v}" for k, v in texts.items()])
        row["rubric_attributes"] = len(rub)
        for attr in KEY_ATTRS:  # the parameters our checks map to, first
            row[f"h_{attr}"] = rub.get(attr, "")
        row["_rubric"] = rub
        row.update(_dataqc_task_completion(dqi[cid]) if cid in dqi else
                   {"autoqc_task_completion": None, "autoqc_task_completion_detail": ""})
        o = ours.get(cid)
        f = (o or {}).get("findings") or []
        row["ours_flag"] = f"{f[0]['kind']}:{f[0]['status']}" if f else ("none" if o else "")
        row["ours_user_verdict"] = verdicts.get(cid, {}).get("verdict", "")
        out.append(row)
    return out


def _sop_line(text: str, field: str) -> str:
    lines = [l.strip() for l in (text or "").splitlines()]
    for i, l in enumerate(lines):
        if l.lower().startswith(field.lower() + ":"):
            rest = l[len(field) + 1:].strip()
            return rest or next((x for x in lines[i + 1:] if x), "")
    return ""


def search(out: Path, attrs: Sequence[str]) -> int:
    with _connect("FTS") as conn:
        subs = _rows(conn, SEARCH_SQL.format(fts=sql_name("FTS_SCHEMA", "public")), {"workflow": setting("FTS_WORKFLOW_ID")})
    by_job: Dict[str, Dict[str, dict]] = defaultdict(dict)
    for r in subs:
        by_job[r["child_job_id"]][r["reviewer_step"]] = r
    rows = []
    for jid, steps in by_job.items():
        order = sorted(steps, key=lambda s: STEP_ORDER.get(s, 9))
        final = steps[order[-1]]
        rub = final["rubric"] if isinstance(final["rubric"], dict) else {}
        if not any(rub.get(a) in ("medium", "discard") for a in attrs):
            continue
        row = {"child_job_id": jid, "reviewer_steps": ";".join(order), "final_step": order[-1],
               "final_decision": final["decision_status"], "submitted_at": str(final["submitted_at"])}
        for a in attrs:
            row[a] = rub.get(a, "")
            for s in ("Reviewer 1", "Reviewer 2"):
                r = steps.get(s)
                row[f"{s.replace('Reviewer ', 'r')}_{a}"] = (r["rubric"] or {}).get(a, "") if r and isinstance(r["rubric"], dict) else ""
        row["other_medium_discard"] = "; ".join(sorted(f"{k}={v}" for k, v in rub.items()
                                                      if v in ("medium", "discard") and k not in attrs))
        rows.append(row)
    with _connect("AUTOQC") as conn:
        aq = {r["child_job_id"]: r for r in _rows(conn, AUTOQC_SQL.format(autoqc=sql_name("AUTOQC_TASKS_TABLE")), {"ids": [r["child_job_id"] for r in rows]})}
    for r in rows:
        a = aq.get(r["child_job_id"], {})
        td = a.get("task_description") or ""
        r.update(objects=_sop_line(td, "Objects"), from_=_sop_line(td, "From"), to=_sop_line(td, "To"),
                 clip_id=a.get("clip_id", ""), batch_id=a.get("batch_id", ""), video_path=a.get("video_path", ""),
                 video_url=a.get("video_url", ""))
    rows.sort(key=lambda r: tuple(["discard", "medium", "perfect", ""].index(r[a]) if r[a] in ("discard", "medium", "perfect", "") else 4
                                  for a in attrs))
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "boundary_cases.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    n_jobs = len(by_job)
    print(f"{n_jobs} reviewed jobs on the workflow; {len(rows)} with {' or '.join(attrs)} medium/discard in the final review")
    for a in attrs:
        print(f"  {a}: " + ", ".join(f"{v}={sum(r[a] == v for r in rows)}" for v in ("discard", "medium", "perfect", "")))
    print(f"  video location found for {sum(bool(r['video_path']) for r in rows)}; "
          f"batches: {len({r['batch_id'] for r in rows if r['batch_id']})}")
    print(f"wrote {out / 'boundary_cases.csv'}")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "search":
        sp = argparse.ArgumentParser(prog="procqc.internal.fts_ground_truth search")
        sp.add_argument("out")
        sp.add_argument("--attrs", nargs="+", default=["recording_start", "recording_end"])
        x = sp.parse_args(argv[1:])
        return search(Path(x.out), x.attrs)
    ap = argparse.ArgumentParser(prog="procqc.internal.fts_ground_truth")
    ap.add_argument("clip_ids")
    ap.add_argument("out")
    ap.add_argument("--ours", default=None, help="termination_v2 run dir (recordings/*.json) to set beside the GT")
    ap.add_argument("--verdicts", default=None, help="review_verdicts.jsonl from our own frame review")
    ap.add_argument("--manifest", default=None, help="manifest.jsonl, for the SOP task title per clip")
    a = ap.parse_args(argv)
    ids = [r["clip_id"].strip() for r in csv.DictReader(open(a.clip_ids)) if r.get("clip_id", "").strip()]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    fts, dq = fetch(ids)
    with open(out / "fts_submissions.jsonl", "w") as f:
        for r in fts:
            f.write(json.dumps(r, default=str) + "\n")
    with open(out / "dataqc_records.jsonl", "w") as f:
        for r in dq:
            f.write(json.dumps(r, default=str) + "\n")
    ours = {}
    if a.ours:
        for p in Path(a.ours).glob("recordings/*.json"):
            r = json.loads(p.read_text())
            ours[r["session"]] = r
    verdicts = {json.loads(l)["session"]: json.loads(l) for l in open(a.verdicts)} if a.verdicts else {}
    sop_task = {json.loads(l)["session"]: json.loads(l)["task"] for l in open(a.manifest)} if a.manifest else {}
    rows = build(ids, fts, dq, ours, verdicts, sop_task)
    # every rubric parameter of the final submission as its own column (h_<parameter>), after the key ones
    all_attrs = sorted({k for r in rows for k in r["_rubric"]} - set(KEY_ATTRS))
    for r in rows:
        rub = r.pop("_rubric")
        for attr in all_attrs:
            r[f"h_{attr}"] = rub.get(attr, "")
    with open(out / "ground_truth.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    # per-parameter distribution over the clips
    with open(out / "rubric_distribution.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["parameter", "perfect", "medium", "discard", "other", "absent"])
        for attr in KEY_ATTRS + all_attrs:
            vals = [r.get(f"h_{attr}", "") for r in rows]
            w.writerow([attr] + [vals.count(v) for v in ("perfect", "medium", "discard")] +
                       [sum(v not in ("perfect", "medium", "discard", "") for v in vals), vals.count("")])
    n = len(rows)
    print(f"{n} clips: {sum(r['in_fts'] for r in rows)} in FTS, {len(fts)} submissions, {len(dq)} DataQC records")
    print(f"human_rejected {sum(r['human_rejected'] for r in rows)}, human_task_flag {sum(r['human_task_flag'] for r in rows)}, "
          f"human_flagged {sum(r['human_flagged'] for r in rows)}")
    print(f"wrote {out / 'ground_truth.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
