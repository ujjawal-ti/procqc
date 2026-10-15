# Redundant repetition as its own check (1 Oct 2026)

Code: `procqc/direct/repeat.py` (candidates + verifier v1), tests `procqc/tests/test_repeat.py`.
Runs: `out/repeat_check/{cc4d, synth_tune}`.

## Method

A redundant repeat is a step performed again after its result was already achieved, beyond the times
the procedure allows, with nothing in between that made the redo needed. Not repeats: a correction
(failure, then redo), a redo because the object changed (mix again after adding an ingredient), strokes
inside one continuous action.

* **Candidates, no model**: count performances per step in the narrated step sequence (cached
  narration and match v1, shared with the other checks); each performance beyond `permitted_repeats`
  is a candidate, with the previous performance as context. An entry the look-alike rule marked as
  continuing the previous one is the same performance.
* **Verifier v1, one video call**, two clips (previous and claimed repeat, padded 2 s, at most 45 s):
  same step again? first result achieved? went wrong in between? object changed in between? verdict
  redundant_repeat / correction / needed_redo / not_a_repeat. Correction is rejected as a repeat but
  noted, for the correction check.

## Data

* Synthetic Lightwheel: 45 videos with a state-changing step duplicated right after itself (identical
  frames), 50 clean. Tuning half 18 + 20 (same families as the off-graph split), held-out 27 + 30.
* CaptainCook4D, 36 recordings: no repeat category in the dataset, but repeated discrete additions
  (a second egg, a second spoonful) are labelled as **Measurement Error**.

## Results

Oracle (rule on the annotators' own step sequences, no model): synthetic 45 / 45 found, 0 of 208 other
variants flagged; CaptainCook4D 1 of 51 recordings flagged (28_49, scallion chopped twice).

| set | candidates | true | verifier v1: confirmed / rejected | precision without → with verifier | cost |
|---|---|---|---|---|---|
| CaptainCook4D, 36 recordings | 14 in 5 recordings | 5 | 5 / 9 | 0.36 → **1.00** | $0.19 |
| synthetic tuning, 38 videos | 6 | 1 | 0 / 6 | 0.17 → – | $0.98 |

**Real data.** All 5 confirmed repeats are real errors that the annotators labelled as measurement
errors: second egg poured (1_36, 1_43, 1_136), second tablespoon of cheese (1_136), second spoonful of
salsa (1_136). Correct rejections: continuations of one performance (oil heated then the stove turned
on; garlic sautéed in bursts) and one **correction** (15_46: the blender jammed, the cup was re-seated
and the puree redone).

**Correction (1 Oct, after scoring against labels).** An earlier version of this report said all 9
rejections were right. Scored against the measurement labels, 3 rejected candidates are on steps where
the annotators labelled a repeated addition (1_36 cheese and salsa, 1_37 salsa). In each, the narration
entries the candidate points at are mis-timed (opening the jar, fetching the spoon), so the clips do not
show the repeat and the verifier's answer is right about the clips. Event level, repeated additions on
the development recipes: detector only 8 TP / 2 FP / 7 FN, with the verifier 5 / 0 / 10 (17 labels in
all, from "N instead of 1" measurement errors). Full numbers in `2026-10-01_scorecard.md`.

**Synthetic data: 1 of 18 candidates.** Not a counting problem (the oracle finds 45 / 45):
* in 12 of 18 the narration has a single entry over the original and its copy. The copies are 1.5-3 s
  of identical frames and the narration samples 1 frame per second;
* in 1 (54d2549a) the second "place blade" was folded into the first by the look-alike continuation
  rule (built for microwave buttons pressed twice in one run);
* in the one true candidate (0ee146d2) the verifier answered "the exact same opening instance", which
  is literally true of a duplicated clip.
The synthetic duplication is physically odd (the object jumps back to its earlier state), so, like the
synthetic swaps for misordering, it is a weak benchmark for this kind.

## Open

* Taxonomy boundary, decided 1 Oct: a repeat of a step whose text states an amount ("pour 1 egg",
  "1 tablespoon of salsa") is reported as a parameter deviation tagged `repeated_addition`
  (`repeat.route`); other repeats stay redundant repeats. Durations are not amounts.
* Recall on real repeats is limited by the narration (one entry for two scoops). A repeat-specific
  counting call would be a detector v2.

## Repeat v2 and correction loops on Assembly101 (9–11 Oct 2026). Concluded

Code: `procqc/direct/repeat_v2.py` (object log, repeat candidates, repeat verifier v2),
`procqc/direct/correction.py` (correction loops, own verifier, decision rules v1 and v2),
`procqc/direct/misorder_instance.py` (order between the rounds of a repeat block, code only).
Data: `out/opensource/assembly101/` (30 toy-assembly recordings, 111.5 min, one general SOP), built by
`procqc/audit/opensource_assembly101.py`. Runs: `out/repeat_check/a101_v2_all30_twoview` and
`a101_v2_all30_twoview_corr_v2`. Scorecard rows: `scorecard.md`.

**Verdict.** The repeat check does not work on this data: 0 of 42 labelled repeats caught. The correction
check catches about half of the labelled loops, with about half of its flags wrong. Both kinds are closed
here; nothing further is planned on them.

**Method in short.**
* One object log per recording: 60 s windows (10 s overlap), each sent in two views (full frame at 2 fps and
  a work-area crop at 5 fps, the box drawn by one Fuelix Gemini frame call per window). The log lists every
  action that leaves a lasting change: performs or undoes, step, object, counterpart, times.
* Repeat candidates: a step done more often per object than the procedure allows. Verifier v2 looks at the
  first performance, the undoing and the redo.
* Correction candidates: an undo followed by a redo of the same step on the same moved object. Its
  verifier asks why the result was undone (a fault in this result, a fault elsewhere, a planned change, or
  none visible).
* A confirmed correction on the same object cancels an overlapping repeat flag (user decision: undoing a
  correct part while fixing another fault is part of that correction).

**Labels used** (Assembly101 coarse labels, plus its fine-grained labels for one rule): 42 redundant repeats,
44 correction loops, 23 misorderings. A repeat whose part beneath was screwed while it was off was moved to
corrections and misordering (fine-grained "screw" actions; the coarse labels have none). That rule lives in
the label builder only; no prompt or pipeline rule names a part, an action or the dataset.

**Results, all 30 recordings ($14.72, about $0.49 and 12 minutes per recording).**

| check | labelled | detector only TP / FP | with verifier TP / FP | with verifier precision / recall |
|---|---|---|---|---|
| redundant repeat v2 | 42 | 21 / 121 | 0 / 7 | 0.00 / 0.00 |
| correction loop, rule v1 | 44 | 31 / 50 | 22 / 22 | 0.50 / 0.50 |
| correction loop, rule v2 | 44 | 31 / 50 | 18 / 9 | 0.67 / 0.41 |
| misordering per object | 23 | 2 / 37 | 1 / 0 | 1.00 / 0.04 |

(The scorecard counts 2 flags on extra undos inside a correction as false; the correction module counts
them apart.)

**Why the repeat check fails.** The verifier called 23 of the 31 candidates that sit on labelled repeats a
correction: it names a fault (usually vague, "not properly aligned") for almost every undo and redo. Of its
7 confirmed flags, 3 are one continuous screwing that the log split in two, 3 sit on labelled corrections,
and 1 is a screw taken out and driven again, which the coarse labels cannot judge.

**Why the correction check is half right.** Of 17 confirmed loops away from any labelled correction, 11 sit
on labelled repeats. The fine-grained labels show 2 of those 11 really fixed another part while this one was
off (the gold is wrong there, under the rule above), 3 had nothing between the removal and the refit (the
verifier invented a fault), and 6 are refits of the same part or unclear from the labels. Of the other 6
loops,
2 are real undos that only the fine-grained labels record and 4 are undos the log made up. Of the missed loops, 10 never became a candidate (the log missed the undo or the
redo) and 5 were rejected because the log had named another part than the one undone.

**Rule v2** (a confirmed correction must show a change in the log while the part was off: another object
worked on, or the part put onto another one). Same verifier answers, no model calls. Precision rose
0.50 → 0.67 and clean recordings with a false loop fell 9 → 2 of 12, but recall fell 0.50 → 0.41 (4 real
loops lost) and repeat false flags rose 7 → 10, because fewer confirmed loops cancel repeat flags. The rule
was found by studying these 30 recordings, so these numbers are not a held-out result. Rule v1 stays the
default.

**What would be needed to go further (not planned).**
* The hard part is not seeing the undo; it is judging whether the undo was needed. Assembly101's
  "shouldn't have happened" depends on knowing the toy's build order, which the general SOP does not hold,
  so the procedure itself would need dependency information between parts.
* The object log misses or misnames small parts and splits one long action into two. Recall of both kinds
  is capped by it.
* An honest test of rule v2 needs Assembly101 recordings not looked at so far (the full mistake set has
  323 loops in 125 recordings).
