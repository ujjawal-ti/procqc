# Direct arm on real omissions: CaptainCook4D, 25 Sep 2026

First test of the AutoQC direct arm (one graph-grounded native-video call per taxonomy kind, then
the adjudicator) on real, human-annotated procedural errors rather than re-cut synthetic ones.

## Data

CaptainCook4D (Apache 2.0): 10 GoPro 360p recordings, two recipes with their **published step
dependency graphs** (DAGs with parallel branches), 5.7–18.5 min each, 128 min in total.
Adapter: `procqc/audit/opensource_cc4d.py`; data under `out/opensource/captaincook4d/`.

| recording | recipe | in-scope labels | other labelled errors |
|---|---|---|---|
| 1_10 | Microwave egg sandwich | omission (first microwave step skipped) | — |
| 1_28 | egg sandwich | omission (first microwave step) | 6 (measurement, technique, timing, preparation) |
| 1_32 | egg sandwich | omission (ramekin not coated), misordering | 6 |
| 1_34 | egg sandwich | omission (ramekin not coated) | 6 |
| 1_14, 1_7 | egg sandwich | clean | — |
| 28_25 | Spicy tuna avocado wraps | omission (mayonnaise measured, never added) | — |
| 28_26 | tuna wraps | 3 omissions (avocado not sliced, not placed; tuna not put on leaves) | 7 |
| 28_2, 28_10 | tuna wraps | clean | — |

Label semantics: 278 of the dataset's 285 "Missing Step" labels are skipped steps with no
timestamps; 7 sit on a timed window in which the step was performed in appearance but not in
substance ("did not add mayonnaise"). Both are kept as omission labels; the latter are removed from
the performed-step segments. Wrong-ingredient/tool and parameter errors (25 labels here) are kept as
findings of kinds the arm does not attempt, so their episodes are not scored as clean; they appear
as false negatives of those kinds.

Sanity check before any model call: replaying each recording's annotated step sequence through its
published graph flags exactly the labelled omission in every error recording and nothing in the
clean ones.

## Three defects the real data exposed, all fixed

1. **Prompt described DAGs as chains.** The step list said "each step depends on the one before
   it" in id order. Every "mixed the bowl before seasoning" misordering the model raised on clean
   recordings was the published graph's correct order. Fix: topologically sorted list, explicit
   "requires step k" per step, and a sentence that unrelated branches may run in either order.
   Chain graphs render exactly as before.
2. **Termination fold used list position.** Omissions "after" a termination in the id list were
   demoted; in a DAG that is arbitrary. Fix: graph descendants of the termination step.
3. **Fold direction.** Even with descendants, a spurious termination hid three true omissions
   (28_26: the person rolled empty wraps and finished; the model called it a recording end). The
   two kinds are one event seen two ways, so now the omissions stay asserted (the steps are missing
   either way) and the co-occurring termination goes to a human. In scoring, an omission and a
   termination on the same step detect each other, with the kind mismatch recorded in the
   confusion table. Applied offline to the stored verdicts; no new model calls.

## Results (strict = confirmed findings; lenient adds human-review items)

| | run 1 (chain prompt) | run 2 (DAG prompt, list fold) | **run 2 re-folded (final)** |
|---|---|---|---|
| omission TP / FP / FN (8 gold) | 3 / 0 / 5 | 2 / 1 / 6 | **5 / 1 / 3** |
| omission precision / recall (strict) | 1.00 / 0.38 | 0.67 / 0.25 | **0.83 / 0.63** |
| omission recall (lenient) | 0.50 | 0.25 | 0.63 |
| misordering TP / FP / FN (1 gold) | 0 / 1 / 1 | 0 / 1 / 1 | 0 / 1 / 1 |
| false off-graph / repeat / termination | 1 / 1 / 1 | 1 / 0 / 1 | 1 / 0 / 0 (termination → review) |
| clean recordings flagged (strict) | 1 of 4 | 0 of 4 | **0 of 4** |
| clean recordings flagged (lenient) | 4 of 4 | 1 of 4 | 1 of 4 |
| routed to human | 40 % | 30 % | 30 % |
| cost | $3.43 | $3.74 | — (offline) |
| cost per recording (12.8 min avg, capped at 900 frames/call) | $0.34 | $0.37 | |

## What it got right and wrong

- **Caught (5):** un-coated ramekin (1_32); mayonnaise measured into the cup, left on the board,
  never added (28_25, confidence 0.98, exact evidence); all three skipped steps of 28_26 (avocado
  never sliced, never placed, tuna never put on the leaves). These are "effect never appears" and
  "ingredient never reaches the bowl" omissions — visible states, the kind of evidence the model
  reads well.
- **Missed (3):** the skipped first microwave step in 1_10 and 1_28, twice. The recipe has three
  microwave steps; the model saw "two intervals", judged the procedure complete, and in 1_28
  reported "stirred before microwaving" instead, which is the propagated consequence of the
  omission (a kind confusion, not a blind spot). 1_34's un-coated ramekin was caught in run 1 and
  reported on the wrong step in run 2: model variance on a 6-minute video at ~2.5 fps.
- **False findings (strict, 3):** utensil washing at the sink reported as an off-graph action (real,
  not annotated by CaptainCook4D, and an addition under our taxonomy); one misordering on a clean
  recording; one omission of salt on 28_2 routed to a human (a plausible annotation gap: the model
  describes pepper being added and no salt).
- **Not attempted:** 25 wrong-ingredient/tool and parameter errors. These need the effect verifier
  with predicates (quantity, temperature, technique) or a dedicated kind prompt; the published
  graphs carry no predicates.

## Reading

On real omissions the direct arm reaches 5 of 8 with one false omission and no clean recording
falsely flagged, at $0.37 per 13-minute recording. The misses are counting failures on repeated
identical steps (three microwave cycles), the same weakness the synthetic set showed for repeats.
The synthetic omissions were harder than these because a re-cut leaves the effect visible; here the
effect genuinely never appears, which is what the model detects. Ten recordings is a probe, not a
benchmark: CaptainCook4D has 140 recordings with Missing Step labels across 24 recipes with graphs,
all downloadable per recording at 360p (55–140 MB each), which is the natural next set.
