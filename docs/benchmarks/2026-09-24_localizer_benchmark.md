# Step-localizer benchmark, 24 Sep 2026

Four arms of the as-built procqc localizer (motion or hand-tracking proposals → VLM step scorer
with graph candidate lists → beam decode → one boundary-refinement round), scored against the
earlier GDM auto-labeling pipelines with that project's own `evaluate_v2.py`, plus the
segmentation metrics from `procqc/audit/temporal_metrics.py`. Model: gemini-3.8-flash via Fuelix.
Localizer settings were the pipeline defaults (window floor 0.9 s, 3 frames per window,
8-frame ±1.5 s refinement, snap within 0.3 s). Nothing was tuned on these videos.

Harness: `procqc/localize/bench_lightwheel.py`. Raw outputs, per-video reports, predictions and
summaries: `out/bench_lightwheel/{oracle,caption}/`, `out/bench_gdm/{proposals,oracle_motion,oracle_tracking}/`,
cross-system scoring in `out/bench_*/evaluate_v2_*.txt`.

## What was compared

| arm | dataset | task graph | proposer | what it measures |
|---|---|---|---|---|
| oracle | Lightwheel held-out 25 (452 GT segments, 1995 s) | chain graph from the video's GT step list | frame motion | alignment quality with the step list known |
| caption | Lightwheel held-out 25 | LLM draft from the one-sentence global caption only | frame motion | detection quality without GT labels (fair vs earlier pipelines) |
| oracle / motion | GDM QC 17 (259 GT segments, 965 s) | chain graph from GT | frame motion | paired baseline for the proposer test |
| oracle / tracking | GDM QC 17 | chain graph from GT | 90 Hz hand tracking | effect of the proposer alone |

The oracle arms know the step list, which the earlier pipelines did not; their label metrics are
therefore not comparable and only localization-only numbers are compared across systems.

## Lightwheel (same 25 held-out videos as the earlier session)

| system | pred / GT | loc-only P / R / F1 at IoU 0.5 | loc+label F1 (cos ≥ 0.2) | boundary-tolerance F1 (0.5 s) | cost |
|---|---|---|---|---|---|
| earlier monolithic v3 (gemini-3.6-flash) | 0.70 | 48.3 / 33.6 / 39.6 | 31.3 | 16.4 | — |
| earlier decomposed pipeline | 0.85 | 48.2 / 41.2 / 44.4 | 31.0 | 24.6 | — |
| procqc, oracle graph, motion | 0.62 | 52.1 / 32.3 / 39.9 | 39.3 (labels given) | 13.1 | $9.60 |
| procqc, caption graph, motion | 0.39 | 50.0 / 19.7 / 28.3 | 18.7 | 8.3 | $10.40 |

Refinement effect (oracle arm, label-aware, micro): F1 at IoU 0.5 26.2 → 36.9; boundary-tolerance
F1 4.1 → 13.1; boundary recall at 0.5 s 29.7 → 40.8 %; starts within 0.5 s 15.7 → 36.7 %.

Why recall is capped (oracle arm, 316 GT segments unmatched at IoU 0.5): 216 had the right label
predicted with boundaries off, 100 never had the label predicted. 29 % of GT segments are shorter
than the 0.9 s window floor. The held-out GT contains no consecutive same-label pairs, so repetition
merging is not a factor. The caption arm drafted 142 steps for 452 GT segments (about 6 per video
against 18 annotated), which caps its recall by construction.

## GDM (17 QC videos with hand tracking)

### Proposal level, no model calls

Macro over videos. `edge` = window edges the localizer scores; `menu` = dense snap candidates the
refiner may use; `ceiling` = GT segments with both endpoints in the menu within the tolerance.

| metric | motion | tracking |
|---|---|---|
| edge boundary recall @0.5 s | 35.9 % | 56.5 % |
| edge boundary recall @0.25 s | 15.9 % | 28.2 % |
| menu boundary recall @0.5 s | 44.4 % | 78.0 % |
| segment ceiling @0.5 s | 19.1 % | 69.6 % |
| median GT-boundary → nearest candidate | 0.58 s | 0.37 s |
| windows per GT segment | 1.8 | 2.2 |
| compute per video | 6.7 s | 0.2 s |

### Localizer level, paired (same graph, scorer, decoder, refinement)

| metric (micro unless noted) | motion, before refine | motion, after | tracking, before | tracking, after |
|---|---|---|---|---|
| F1 at IoU 0.5 (label-aware) | 28.3 | **43.2** | 35.3 | 40.7 |
| P / R at IoU 0.5 | 37.3 / 22.8 | 57.0 / 34.7 | 42.0 / 30.5 | 48.4 / **35.1** |
| F1 at IoU 0.3 | 47.0 | 56.6 | 53.2 | **56.8** |
| boundary-tolerance F1 (0.5 s) | 4.8 | 19.7 | 13.9 | **20.6** |
| F1@10 / F1@25 / F1@50 (macro) | 69.2 / 54.3 / 29.7 | 73.5 / 63.5 / 45.5 | 70.7 / 61.3 / 40.4 | **74.1 / 66.1 / 46.7** |
| Edit (macro) | 71.8 | 71.8 | 72.6 | **72.6** |
| MoF (macro) | 51.6 | **61.3** | 55.5 | 59.6 |
| boundary recall @0.5 s (macro) | 25.5 % | 43.4 % | 41.0 % | **45.3 %** |
| GT starts within 0.5 s | 14.3 % | 38.7 % | 35.8 % | **43.9 %** |
| mean nearest start error | 4.31 s | 4.05 s | 2.92 s | **2.83 s** |
| pred / GT | 0.61 | 0.61 | 0.73 | 0.73 |
| cost | | $4.97 | | $6.02 |

Cross-system (loc-only, IoU 0.5, `evaluate_v2.py`): earlier Gemini 3 Flash 53.0 / 33.6 / 41.1;
earlier er2 56.4 / 38.4 / 45.7; procqc motion 64.6 / 39.4 / 48.9; procqc tracking 55.3 / 40.2 / 46.5.

Per video, tracking improves F1 at IoU 0.5 on 10 of 17 and hurts on 5. The losses are the
continuous-motion videos where hand speed has no minima (e3fff5da −0.37 with 5 windows instead of
10; 627cc09c −0.29; 112437e8 −0.28). The gains are the repetitive fine-action videos the proposal
study flagged (2b9b7e58 +0.21, 385f3d9b +0.18, 07aafe02 +0.17, 1b22371b 9 → 29 predictions).

Failure attribution after refinement (GT segments unmatched at IoU 0.5): motion 126 boundaries-off,
43 label-never-predicted, 23 wrong-label overlaps; tracking 126, 42, 37. Predictions with no GT
overlap at IoU 0.3: motion 17 of 158, tracking 24 of 188.

## Conclusions

1. **On GDM the as-built localizer beats both earlier pipelines** on every localization threshold
   and on boundary tolerance, with the step list given (F1 at IoU 0.5: 48.9 vs 45.7 and 41.1).
2. **On Lightwheel it only matches the older monolithic system and trails the decomposed one.**
   The gap is under-segmentation: 0.62 predictions per GT segment, with 29 % of GT under the 0.9 s
   window floor. Refinement recovers boundaries that exist but cannot create ones the proposer
   never offered.
3. **Hand tracking raises the proposal ceiling from 19 % to 70 % of segments, but the localizer
   realizes only part of it.** Before refinement tracking is clearly better (F1 35.3 vs 28.3,
   boundary-tolerance 13.9 vs 4.8). After refinement the two converge: tracking keeps the lead on
   recall, boundary precision-at-tolerance and the segmentation F1s, motion regains precision.
   The extra tracking windows are shorter and the scorer mislabels more of them (37 vs 23 wrong-label
   overlaps), so the bottleneck moves from the proposer to per-window labeling.
4. **Caption-only graphs are not enough** to reproduce annotator granularity: 6 steps per video
   drafted against 18 annotated. A client SOP or annotation guideline, not a caption, is the
   realistic input for the graph builder.

## Levers indicated, not yet run

- Lower the window floor and gap (0.9 s → 0.5 s) on datasets with sub-second actions; the proposal
  study suggests this is the single largest recall lever for motion, at higher scoring cost.
- Use tracking for the snap menu and refinement, motion or the union for windows, so the
  continuous-motion videos keep their cuts (the 5 videos where tracking lost).
- Second refinement round (bisect once more); refinement was the largest gain in every arm.
- Better per-window labeling on short windows: more frames per short window, or the distilled
  window head trained from the item log (see `procqc/OPTIMIZATION.md`).
- Cost: $0.29–0.42 per video at this model; scoring and refinement split evenly. The distilled
  heads target both.
