# Interactive architecture walkthrough

A single web page that walks stakeholders through the procqc pipeline using one real
episode (`hairdryer_trunc44`, the 44 s truncation of the hair-dryer recording). Every
frame, number, JSON excerpt and model answer on the page comes from files the pipeline
produced (`out/audit_demo3/verdicts/hairdryer_trunc44.json`, `out/hairdryer_graph.yaml`,
`out/laya_training_export/`) or is recomputed deterministically from the video (motion
signal, boundary proposals, symbolic verification, lint). Nothing is mocked.

## Files

| file | purpose |
|---|---|
| `procqc_pipeline_walkthrough.html` | **share this one** — self-contained (data inlined, ~0.9 MB), opens by double-click in any browser |
| `index.html` | same page, loads `demo_data.js` next to it; edit this when changing the page |
| `demo_data.js` / `demo_data.json` | the real episode data, generated |
| `build_demo_data.py` | regenerates the data files and the standalone HTML |

## Using the page

* **Play walkthrough** animates through the 12 stages (input → task graph → boundaries →
  localizer → refinement → graph verifier → effect verifier → reconcile → adjudicator →
  verdict → item log/export → audit). Arrow keys step, space plays/pauses.
* Click any box in the flow diagram, or any numbered button, to jump to that stage.
* Each stage panel shows what the component does, which source files implement it, the
  real input it received and the real output it produced, plus calls, tokens, cost and
  wall time where a model was involved.
* The episode timeline gains layers as stages complete (signal, windows, labels,
  refined boundaries, judged frames, findings). Hover it to see the nearest frame the
  pipeline actually looked at.

## Regenerating

From the repository root:

```bash
uv run python docs/architecture/build_demo_data.py
```

Optionally pass the URL of the Understand-Anything code dashboard so the header gains an
"Open code dashboard" link:

```bash
uv run python docs/architecture/build_demo_data.py http://localhost:5173
```

To show a different episode, change `EPISODE`, `VERDICT`, `GRAPH` and `SOP` at the top
of `build_demo_data.py`; the page itself is episode-agnostic.

To preview `index.html` locally (needed because browsers block `demo_data.js` on some
`file://` setups):

```bash
python3 -m http.server 8765 --directory docs/architecture
```

## Code-level view

The Understand-Anything knowledge graph of the repository lives in `.ua/knowledge-graph.json`
and is browsed with the plugin's dashboard (`/understand-dashboard` in Claude Code). It
complements this page: this page follows the data through the pipeline; the dashboard
shows every module, class and function and how they call each other.

## Second page: AutoQC results on real recordings

`qc_demo_captaincook4d.html` (self-contained, ~4.5 MB) shows the direct arm v2 (narrate → judge)
on 10 CaptainCook4D recordings with real error labels: an overview with strict per-kind scores, then
per recording the verdict and cost split, the ground-truth labels with a detected/not-detected mark,
the recipe graph with each step marked narrated / labelled missing / predicted, the narration
timeline with one frame per entry (green border = matched to a step, red = cited by a finding;
hover shows the state change), and every finding with its narration citations, adjudicator
rationale, devil's-advocate argument and frames from the finding and context spans. A collapsible
row shows the earlier per-kind-video arm's findings on the same recording.

Rebuild after a new run:

```bash
uv run python docs/architecture/build_qc_demo.py \
    --run out/opensource/captaincook4d/narrate --labels out/opensource/captaincook4d/labels.jsonl \
    --compare out/opensource/captaincook4d/direct_kinds_refold \
    --cost-runs out/opensource/captaincook4d/narrate_v1,out/opensource/captaincook4d/narrate_probe \
    --out docs/architecture/qc_demo_captaincook4d.html
```

`--cost-runs` merges the narration cost from earlier runs of the same recordings when the latest
run re-judged from cached narrations. The template is `qc_demo_template.html`; the same builder
works for any run directory produced by `procqc.direct.arm` or `procqc.audit.cli run` that has a
matching labels file.
