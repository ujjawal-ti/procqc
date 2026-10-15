# Documentation index

These documents were written in the research workspace (`Procedural Errors/`), where the code lived under other
module paths. The commands and file paths inside the reports use those workspace paths. The table at the end maps
each one to its place in this repository.

## Start here

| Document | What it is |
|---|---|
| [Validation_Report_and_Agentic_Pipeline.md](Validation_Report_and_Agentic_Pipeline.md) | The taxonomy validation against the literature, and the agreed design: graph-grounded, per-kind agentic QC |
| [benchmarks/2026-10-11_taxonomy_report.md](benchmarks/2026-10-11_taxonomy_report.md) | Where each error-type check stands, with scores |
| [architecture/2026-10-13_rubric_task_execution_mapping.md](architecture/2026-10-13_rubric_task_execution_mapping.md) | How the Snowbird rubric's task-execution parameters map onto our checks, and the build order |
| [benchmarks/2026-10-13_gestural_anchoring_check.md](benchmarks/2026-10-13_gestural_anchoring_check.md) | Recording start and end signal check on internal headset data |
| [benchmarks/2026-10-14_task_execution_checks.md](benchmarks/2026-10-14_task_execution_checks.md) | Lighting, navigation, efficiency and grouping checks on internal headset data |
| [OPTIMIZATION.md](OPTIMIZATION.md) | Cost and speed notes, and what post-training could change |

Source documents: `Physical AI Data Quality Control.docx` (the QC guideline draft) and the
`..._Physical_AI__Procedural_ErrorsMistakes.pdf` (the procedural error taxonomy).

## Folders

* `benchmarks/`: one dated report per check or experiment, plus the shared scorecard
  ([scorecard.md](benchmarks/scorecard.md)), the published error distributions
  ([error_taxonomy_distributions.md](benchmarks/error_taxonomy_distributions.md)) and the synthetic Lightwheel set.
* `architecture/`: the hybrid architecture diagram, the interactive pipeline walkthrough (`index.html`; open it in a
  browser), the CaptainCook4D review demo, the taxonomy readiness page, the graph-flaw safeguards note, and the
  scripts that build these pages.
* `research/`: the literature review on wrong tool / object detection.
* `taxonomy/`: the CaptainCook4D preparation errors that are not a wrong tool.
* `prompts/`: the judge prompts as rendered for one real recording.

## Latest headset results: pass or discard (15 Oct 2026)

Reviewer scores are folded into two outcomes: perfect and medium count as pass, discard counts as discard. Our
"needs review" also counts as discard. Data: Set A (the 100 Meta_Pilot test recordings) and Set B (70 recordings
that reviewers flagged at the start or end).

| Check | Precision | Recall |
|---|---|---|
| Recording start | 19/20 | 19/23 |
| Recording end | 6/8 | 6/9 |
| Task-specific requirements (termination and broken recordings) | 2/3 | 2/7 |
| Task-specific requirements, adding wrong destination | 2/11 | 2/7 |
| Whole recording (any check) | 25/36 | 25/32 |

A broken-recording rule (under 10 s, or no task item seen) catches every reviewer discard on lighting, navigation,
efficiency, grouping, handling and scene state, at precision between 1/4 and 3/4. None of the checks predicts the
reviewers' medium scores yet.

## Corrections to the reports

* Gestural anchoring report, "all 9 end discards are flagged": that count treats our medium as flagged. With medium
  counted as pass, 6 of the 9 end discards are caught (the table above). The same sentence appears in the rubric
  mapping document.

## Code paths: workspace to this repository

| Workspace (`Procedural Errors/procqc/...`) | This repository |
|---|---|
| `direct/arm.py` (video client) | `procqc/video_client.py` |
| `direct/narrate_judge.py` (narration and step matching) | `procqc/judges/narration.py` (`_dag` is `step_dag`) |
| `direct/termination.py` | `procqc/judges/termination.py` |
| `direct/termination_v2.py` | `procqc/judges/termination_v2.py` |
| `direct/omission.py` | `procqc/judges/omission.py` |
| `direct/misorder*.py` | `procqc/judges/misordering.py` |
| `direct/offgraph.py` | `procqc/judges/offgraph.py` |
| `direct/repeat*.py` | `procqc/judges/repeat.py` |
| `direct/wrongtool*.py` | `procqc/judges/wrongtool.py` |
| prompt constants inside each module | `procqc/prompts.py` (look up with `prompts.get(name)`) |
| per-kind runs started module by module | `procqc/run.py` (all selected checks over one manifest) |
| `audit/scorecard.py` | `procqc/evaluate.py` |
| `audit/demo_export.py` (converts saved workspace runs) | its output is read by `procqc/demo/` |
| `audit/fts_ground_truth.py` | `procqc/internal/fts_ground_truth.py` |
| `audit/s3_fetch.py` | `procqc/internal/s3_fetch.py` |
| the headset manifest (built ad hoc) | `procqc/internal/manifest.py` |
| `signals/{gesture_verify,start_marker_v2,walk_v2,pickplace,trips,lighting,nav_manip,tsr}.py` | `procqc/signals/`, same names (`auc` moved to `procqc/signals/stats.py`) |
| `Physical AI/procqc` `signals/sensors.py` (the standard sensor event log) | `procqc/signals/sensors.py` |
| `graph/` | `procqc/graph/` |
| `out/internal/meta_pilot/{sop,graph}/` | `examples/meta_pilot/{sop,graph}/` |

Not carried over (research only): `localize/`, `adjudicate/`, `verify/`, `itemlog/`, `pipeline.py` with
`audit/runner.py`, `rubric.py`,
the synthetic-error and open-source dataset tools in `audit/`, `direct/correction.py`, and the Lightwheel tracking
signals. Their reports stay here as the record of what was tried.

Two differences change results:

* The narration prompt in `procqc/prompts.py` is a rewrite without examples. The pick/place pilot (8 of 11 exact)
  was run with the workspace prompt, so it needs a paid re-check with this one.
* Each judge here is one version of its check (the one in its module docstring), not every variant the reports
  compare.
