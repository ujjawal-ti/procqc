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
  judges/           the per-kind checks (one module per kind) and the shared narration
  run.py            batch runner over a manifest
  evaluate.py       scorecard against a labels file
tests/              tests that need no data and make no model calls
examples/           a small hand-written example graph and demo sequences
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

Run the tests:

```bash
python3 -m pytest
```

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
- Not handled yet: stereo side-by-side input (one eye), the end-of-task signal protocol, pauses, and
  checks of the v2 graph's acceptance criteria and constraints.
