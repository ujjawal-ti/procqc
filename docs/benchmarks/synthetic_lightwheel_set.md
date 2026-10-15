# Synthetic procedural-error set from Lightwheel QC videos

Built 24 Sep 2026 with `procqc/audit/synth.py` (seed 7). Data under `out/synth_lightwheel/`
(not versioned; 2.0 GB). Regenerate with:

```bash
uv run python -m procqc.audit.synth build --n-videos 50 --out out/synth_lightwheel --workers 4
```

## Sources

50 Lightwheel recordings, chosen from the 82 that are 20–120 s long with at least 4 annotated
steps, stratified by duration, none from the 25 held-out videos used in the localizer benchmark.
Median source length 60.5 s, median 15 annotated steps. Each source gets a chain task graph built
from its own GT step list (`graphs/<video_id>.yaml`; one node per distinct step description,
`permitted_repeats` for repeated descriptions, no predicates).

## Variants (254 videos, 247 min)

| kind | n | how it is made | label finding | caveat |
|---|---|---|---|---|
| clean | 50 | re-encoded original | none (`clean: true`) | — |
| omission | 42 | one non-terminal **unit of work** removed: consecutive GT steps on one object (e.g. pick up X / arrange X / place X), containing a state-changing verb, >= 1.5 s, at most 3 steps | one `omission` per removed state-changing step, at the cut time | the removed unit's effects may remain visible later; the pipeline's correct answer is `offcamera_step` or an omission needing review (counted via kind alias) |
| early_termination | 39 | recording cut before the last unit of real work (60 %) or the one before it (40 %); trailing "stand up" / "reposition" steps go with it; never more than 60 % of the video removed | `early_termination`, first missing state-changing step | faithful |
| addition_repeat | 45 | a state-changing, single-occurrence step (>= 1 s) duplicated right after itself | `addition_repeat`, step id, span of the second copy | identical frames repeat |
| misordering | 28 | two adjacent units about different objects swapped, both with state-changing steps | `misordering`, the step now preceding its predecessor, span of the moved unit | physically inconsistent for state-changing steps |
| addition_offgraph | 50 | a state-changing 1.5–6 s step from another task's recording spliced in after a unit | `addition_offgraph`, no step id, span of the insert | scene change accompanies the insert; one variant (`6e22f989_ins09`) has a 0.87 s insert from before the minimum was enforced |

Why units and verbs: Lightwheel annotates micro-adjustments and body movements as steps
("reposition the pencil holder", "arrange the stack", "sit down", "stand up", "move toward the
table"). Removing, repeating or moving one of those is not a procedural error under the taxonomy's
boundary rules, and a first build that picked raw GT steps produced exactly such non-errors
(e.g. cutting the release phase of "place the stack of books" after "arrange the stack"). The
generator therefore (a) groups consecutive steps on the same object phrase into a unit, (b) only
targets units/steps whose head verb is state-changing (`STRONG_VERBS` in `procqc/audit/synth.py`;
`WEAK_PHRASES` exclude "turn around", "toward", "walk"), (c) requires >= 1.5 s per removed unit and
>= 1 s per repeated step, and (d) only targets steps whose description occurs once, so every label
is a genuine violation of the chain graph. Videos whose tail or interior offers no such unit simply
lack that kind, which is why counts are below 50.

A verification pass (`docs/benchmarks/` notes, 24 Sep) rendered frame strips around every kind's
injection point and audited all variants for weak verbs and sub-second footage changes: 0 weak
targets, 1 short insert (noted above).

Severity in the labels: `major` for omission, misordering, early termination, off-graph addition;
`minor` for repeats.

## Not covered

Wrong tool/object, correction loops and step-parameter deviation cannot be produced by re-cutting
one recording. Together they are 55–65 % of published procedural-error labels
(`error_taxonomy_distributions.md`), so any baseline on this set covers the "sequence" half of
the taxonomy only. Real footage is needed for the rest: CaptainCook4D (Apache 2.0, downloadable)
has 410 wrong-ingredient/tool, 1,076 parameter and 795 order errors with step annotations and is
the natural next source.

## Files

| file | content |
|---|---|
| `videos/<episode_id>.mp4` | `<src8>_clean`, `_omitNN`, `_termK`, `_repNN`, `_swapNN`, `_insNN` |
| `labels.jsonl` | one `EpisodeLabel` per variant, annotator `synthetic`: findings, re-timed GT segments, duration, provenance in `meta` |
| `manifest_all.jsonl` | batch-runner rows for all variants |
| `manifest_baseline_literature.jsonl` | 50 clean + up to 100 error episodes: 50 clean + errors in the published ratio with design floors (`mix_literature.json`) |
| `manifest_baseline_uniform.jsonl` | 50 clean + 20 per kind (`mix_uniform.json`) |
| `manifest_smoke.jsonl` | 15 episodes, 3 per kind, for the pipeline smoke test |
| `index.json` | selection, per-variant clip lists (source spans in output order), render times, caveats |

## Scoring

```bash
uv run python -m procqc.audit.cli run   out/synth_lightwheel/<manifest>.jsonl out/synth_lightwheel/<run> --workers 2
uv run python -m procqc.audit.cli metrics out/synth_lightwheel/<run>/verdicts out/synth_lightwheel/labels.jsonl
uv run python -m procqc.audit.cli metrics out/synth_lightwheel/<run>/verdicts out/synth_lightwheel/labels.jsonl --statuses confirmed,needs_human
```

`metrics` maps predicted `offcamera_step` to omission, `goal_unmet` to early termination and
`precondition_conflict` to misordering before matching (`KIND_ALIASES` in `procqc/audit/metrics.py`),
collapses an early-termination finding to its first missing step, and reports per-kind P/R/F1,
clean-episode false-positive rate with Wilson CI, verdict accuracy, review rate, kind confusion,
calibration/ECE and the EDA/AUC/MoF/F1@k/Edit temporal metrics from the label segments.
