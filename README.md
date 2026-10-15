# procqc

Procedural-error quality control for recorded demonstrations of a written procedure (SOP), by a person
with a headset camera or by a robot. A task graph drafted from the SOP is the reference. Per-kind checks
compare each recording with it and report flags and a human review list.

## Layout

```
procqc/
  config.py         settings from .env (Fuelix, Google AI Studio, cache, retries)
  prompts.py        every static system prompt, versioned, looked up by name with prompts.get()
  llm_client.py     Fuelix (OpenAI-compatible) client: text and frame calls, cache, cost accounting
  video_client.py   Google AI Studio client for native video, and the ffmpeg clip cutter
  pricing.py        per-stage token, cost and latency accounting
  graph/            task graph schema (v1, v2), linter, operations, SOP drafters, CLI
  signals/frames.py frame access
  signals/sensors.py headset sensor event log (gestures, bends, walking, standing still, grip candidates)
  signals/*.py      headset checks: gestures, walk v2, pick/place, trips, lighting, navigation, TSR
  judges/           the per-kind checks (one module per kind) and the shared narration
  internal/         internal data access: FTS reviewer labels, S3 download, headset manifest
  run.py            batch runner over a manifest
  evaluate.py       scorecard against a labels file
  demo/             review demo: a static site over run folders, and a local server for it
tests/              tests that need no data and make no model calls
examples/           a small hand-written example graph and demo sequences; meta_pilot/ holds the 11
                    internal SOPs and their drafted v2 graphs
docs/               reports, benchmarks, architecture and research notes (index: docs/README.md)
```

## Checks

| kind | how | output |
|---|---|---|
| early termination | one video call on a clip of the final moments | flag or review |
| omission | code finds candidates from the narrated step sequence; a video verifier checks each | router |
| misordering | code finds candidates from the step order and dependencies; video verifier v2 | router |
| off-graph addition | text call for the role of each unmatched entry; a video verifier checks each | filter |
| redundant repeat | code counts performances against the allowed count; a video verifier checks each. Repeats of a step that states an amount are reported as parameter deviation (`repeated_addition`) | filter |
| wrong tool / object | frame calls: find the moment, zoom in, closed question asked 3 times with shuffled options, relation rule | flag or review |

Every check except termination reads one shared narration of the recording: one video call (cached on
disk) and one text call that matches entries to steps.

Routing (`judges/base.py`):
- `confirmed` becomes a flag;
- `needs_review` goes to the review list;
- `rejected` goes to review for **omission** and **misordering** (router: the verifier's explanation is
  kept, nothing is dropped) and is dropped for the other kinds (filter: it stays visible in `candidates`).

## Setup

```bash
python3 -m pip install -e ".[dev]"
```

```bash
cp .env.example procqc/.env
```

Fill in `FUELIX_API_KEY` and `GOOGLE_API_KEY`. `ffmpeg` must be on the PATH for the verifier clips.

## Use

Draft and lint a task graph from an SOP:

```bash
python3 -m procqc.graph.cli draft-v2 SOP.txt graph.yaml --task-id my_task
```

```bash
python3 -m procqc.graph.cli lint graph.yaml --sop SOP.txt
```

Run the checks. The manifest has one JSON object per line: `{"episode_id", "video", "graph"}`.

```bash
python3 -m procqc.run manifest.jsonl out/run1 --kinds omission,misordering --workers 2
```

Score a run. The labels file has one line per recording: `{"episode_id", "findings": [{"kind", "step", "start", "end"}]}`.

```bash
python3 -m procqc.evaluate out/run1 labels.jsonl
```

Build and open the review demo. It has a menu per error kind (a metrics dashboard and every event:
flagged, needs review, dropped by the verifier, missed labelled errors, clean recordings) and a menu of
recordings (the video with a timeline of its events and labelled errors). The config lists datasets as
`{"name", "run_dir", "labels", "manifest", "splits"}`; see `procqc/demo/build.py`.

```bash
python3 -m procqc.demo.build demo_config.json out/demo_site
```

```bash
python3 -m procqc.demo.serve out/demo_site --port 8765
```

Then open http://127.0.0.1:8765. Videos are served from their local paths, never copied.

Write the sensor event log for headset sessions (no model calls). Each session folder holds `session.json`,
`hmd.jsonl` and `hand-left/right.jsonl`. The log lists thumbs-up gestures (with start and end markers), bends
(on floor tasks, one per pick-up or put-down, with the acting hand and the spot), walking, standing still and
grip candidates. Times are in video seconds. Grip candidates are marked low reliability: the video has to
confirm them. Thresholds are in `SensorSettings`.

```bash
python3 -m procqc.signals.sensors path/to/sessions --out events.jsonl
```

Run the tests:

```bash
python3 -m pytest
```

## Internal headset data

Recordings from the headset capture app: a video per session and a sensor folder (session.json with the task
title and SOP text, head and hand tracking at 72 Hz). The checks map onto the Snowbird rubric; see
[docs/architecture/2026-10-13_rubric_task_execution_mapping.md](docs/architecture/2026-10-13_rubric_task_execution_mapping.md)
for what each covers and [docs/README.md](docs/README.md) for the latest scores.

The internal data tools need their own extra and credentials:

```bash
python3 -m pip install -e ".[internal]"
```

Fill the `FTS_*`, `DATAQC_*`, `AUTOQC_*` and `AWS_*` names in `procqc/.env`. The database queries are read-only.
Reviewer labels are used only to score; no model sees them.

Steps, in order. Steps 1 to 4 and 8 make no model calls.

1. Reviewer labels and a sample to download: `python3 -m procqc.internal.fts_ground_truth search OUT --attrs <parameter>`,
   then `python3 -m procqc.internal.s3_fetch select|list|get ...` (`list` shows the download size first).
2. Sensor events: `python3 -m procqc.signals.sensors SENSOR_ROOT --out events.jsonl`. For the walks, walk v2
   (`python3 -m procqc.signals.walk_v2 events.jsonl SENSOR_ROOT events_walk_v2.jsonl`) replaces the standard
   ones, which miss slow walkers.
3. SOPs and graphs: `python3 -m procqc.internal.manifest sops SENSOR_DIR SOP_DIR`, then draft one v2 graph per
   SOP with `python3 -m procqc.graph.cli draft-v2 SOP OUT.yaml --task-id ID` (one text call; the 11
   Meta_Pilot graphs are in `examples/meta_pilot/`).
4. Manifest: `python3 -m procqc.internal.manifest build VIDEO_DIR SENSOR_DIR SOP_DIR GRAPH_DIR manifest.jsonl --events events.jsonl`.
5. Early termination and wrong destination (one video call per recording):
   `python3 -m procqc.judges.termination_v2 run manifest.jsonl OUT --items-rule split`.
6. Start and end signal (frame calls only where the sensor log has no clear two-hand thumbs up):
   `python3 -m procqc.signals.gesture_verify events.jsonl VIDEO_DIR OUT --verifier v2 --termination TERMINATION_OUT`.
7. Pick/place events (one narration call per recording, about $0.04):
   `python3 -m procqc.signals.pickplace manifest.jsonl events_walk_v2.jsonl TERMINATION_OUT OUT`.
8. Rule checks over the logs: `procqc.signals.trips` (efficiency, grouping), `procqc.signals.nav_manip`,
   `procqc.signals.lighting`, `procqc.signals.tsr`. Each prints its usage with `--help` and scores itself
   against reviewer labels with `--gt`.

Status: the discard side works for the recording start and end and for a broken-recording rule. No check
predicts the reviewers' medium scores yet. The narration prompt here is an example-free rewrite, so the
pick/place pilot needs a paid re-check before its numbers carry over.

## Prompts

All static system prompts live in `procqc/prompts.py`. Each one has a name, a version and the module that
uses it, and the code reads them only through `prompts.get(name)`, so they can move to Langfuse without
changing the callers. Dynamic content (the procedure, the narration, clip windows, answer options) is
built in code and sent as the user message.

The prompts state principles only, with no example objects, actions or keyword lists. `tests/test_prompts.py`
enforces this and checks that every registered prompt is used.

## Status and caveats

- The versions here are the ones chosen from earlier benchmarks: match v1, omission v1, misordering
  verifier v2 (as a router), off-graph v1, repeat v1, termination on video, wrong tool v6.
- The prompts in this repository are new example-free rewrites of the benchmarked prompts. **They have
  not been benchmarked yet.** Because the prompt text is part of the cache key, the first run makes fresh
  model calls.
- The amount rule for repeats (`judges/repeat.py`) is a new general pattern; it replaces a word list and
  is covered by unit tests only.
- Not handled yet in the per-kind runner (`run.py`): stereo side-by-side input (one eye), the end-of-task
  signal protocol, pauses, and checks of the v2 graph's acceptance criteria and constraints. For headset
  data, `internal/s3_fetch.py` cuts one eye and the headset checks above handle the start and end signals.
