# Per-taxonomy report: where each check stands (11 Oct 2026)

One section per error type. Each covers our result, where the check works or may work, where it doesn't or
may not, how hard the error type is, how hard the data is, and what published work reports.

Sources, nothing new read for this report:
* our numbers come from `scorecard.md` and the per-kind reports in this folder;
* published numbers come from our earlier research: `../Validation_Report_and_Agentic_Pipeline.md`,
  `error_taxonomy_distributions.md` and `../research/2026-10-04_wrong_tool_detection_methods.md`.

Where a number below says "held-out", the check was frozen before that set was run. Where it says "tuning"
or "found on this data", the number is optimistic.

## Summary

| error type | status | best honest number (with verifier unless stated) | error type difficulty | data difficulty | best published |
|---|---|---|---|---|---|
| Early termination | works on synthetic; no real positives | synthetic held-out 10 / 10, 0 / 10 false; real (CaptainCook4D) 0 / 10 false | easy | easy on cut clips; real ones untested | not labelled in any egocentric dataset |
| Omission | usable with human review | CaptainCook4D held-out: 6 / 8 recordings, 0 / 7 false; events precision 0.92, recall 0.58 | medium | medium to hard | CaptainCook4D missing step, zero-shot on step segments: F1 4.4; EgoPER pooled F1@0.5 33.0 |
| Misordering | usable; flag every candidate | CaptainCook4D held-out, no verifier: 10 / 10 recordings, 0 / 5 false | medium | medium (needs a dependency graph) | CaptainCook4D order, zero-shot on step segments: F1 22.3; Assembly101-O pooled, average F1 75.9 on annotator sequences, 53.5 from video |
| Off-procedure addition | works for other-room splices only | synthetic 20 / 20, 0 / 20 false; real 0 false on 36 recordings (no labels) | hard | no real labelled test | no per-type number in our notes |
| Redundant repeat | does not work on dense undo/redo | CaptainCook4D 5 / 5 confirmed real; Assembly101 0 / 42 | hard | hard | none: only EPIC-Tent labels it (3 labels) |
| Correction loop | half right | Assembly101: 22 / 44, precision 0.50 | medium to hard | hard | labelled in Assembly101, EgoPER, HoloAssist; no detection number in our notes |
| Wrong tool / object | not working on unseen tasks | CaptainCook4D unseen recipes: 16 / 24 recordings, 8 / 20 clean flagged; precision 0.45, recall 0.31 | hard | hard | CaptainCook4D Preparation on step clips: recall 56.0 zero-shot, 76.9 trained (unseen); overall precision about 20 % |
| Parameter deviation | only repeated additions built | development 5 / 0 / 10 (TP / FP / FN); held-out 0 of 2 | hard | hard | CaptainCook4D on step clips, unseen, zero-shot recall: measurement 63.3, timing 65.0, technique 26.1, temperature 33.3; precision not per type |
| Gestural anchoring (start / end signal) | discard works; medium does not | internal, 100 recordings, against reviewer scores (all perfect): signal 2 false confirmed with verifier v1, 0 with v2; timing 2 s: end 23 medium + 1 discard, start 30 medium + 1 review. 70 reviewer-flagged recordings: discard end 9 / 9 flagged, start 19 / 23 to discard or review, our discards 15 / 16 agree; medium no better than chance (AUC 0.63 end, 0.43 start) | easy | easy with head-mounted sensors | none in our notes |

Except for gestural anchoring (section 9, added 12 Oct 2026), none of these has been measured on internal
data, because the internal recordings have no error labels yet. Gestural anchoring is compared with the
human reviewers' rubric scores, which exist for every internal recording.

---

## 1. Early termination

**Our result.** `procqc/direct/termination.py`; report `2026-09-28_termination_check.md`.
* Synthetic tuning: 9 / 10 caught, 0 / 10 false.
* Synthetic held-out: 10 / 10 caught, 0 / 10 false.
* CaptainCook4D: no terminations labelled. 0 / 10 clean recordings flagged with the verifier, and 1 / 10
  without it.
* Cost: about $0.01–0.02 per recording.

**Works or may work.**
* Recordings that end before the last step's result appears.
* Internal data should suit it. The check never looks for a thumbs-up: it judges from the final moments
  whether the last required step was done and the goal state is present. On internal data the final
  thumbs-up (found by the head-mounted sensors in 100 / 100 recordings) can only tell it where the end is.
  A missing thumbs-up is not evidence that the task is incomplete: the check then judges at the end of
  the clip, and the missing gesture is a separate protocol note.

**Doesn't or may not.**
* A task whose last step looks like a middle step. One synthetic miss stopped at a point that matches how
  the procedure ends.
* A real stop is subtler than a clean cut: the person may put the tools down mid-step. No real positives
  have been tested.
* Goal states the camera cannot see.

**How hard the error type is.** Easy. It is one decision per recording: is the final result present at
the end?

**How hard the data is.** Easy on synthetic cuts. Real terminations are missing from every dataset we have.

**Published.** No egocentric dataset labels early termination. They record until the task is done, so the
pooled distribution has 0 labels. The nearest evidence comes from robot data: DROID's idle filter, and
Siemens' "incomplete reset or premature release" findings.

## 2. Omission

**Our result.** `procqc/direct/omission.py`; report `2026-09-30_omission_and_verifier_benchmark.md`.
* CaptainCook4D held-out:
  * with verifier: 6 / 8 recordings, 0 / 7 false; events 11 / 1 / 8 (precision 0.92, recall 0.58);
  * without verifier: events 14 / 9 / 5 (precision 0.61, recall 0.74).
* CaptainCook4D development, with verifier: 10 / 14 recordings, 0 / 7 false; events precision 0.69,
  recall 0.32.
* On the annotators' own step sequences the rule is perfect: 27 / 27 recordings, 0 / 24 false. So the
  losses come from matching narrated actions to steps.
* The verifier is used as a router: a step it rejects goes to human review and is not dropped.

**Works or may work.**
* Steps with a distinct, visible action and a lasting result.
* Short internal SOPs with few steps.

**Doesn't or may not.**
* Look-alike repeated steps (one of three microwave presses).
* Brief steps, and steps done off camera.
* A state already satisfied before recording ("already washed").
* Optional or conditional steps the SOP does not mark.

**How hard the error type is.** Medium. An absence is never seen; it is inferred from the full step list.
It also needs a rule for which performance counts as which step.

**How hard the data is.** Medium to hard. CaptainCook4D recordings run 6–18 minutes at 360p, with many
similar actions. Internal clips are short (under 2 minutes) but fisheye and wide.

**Published.**
* EgoPER error detection, pooled over all error types: best F1@0.5 is 33.0 (GTG2Vid), and best EDA / AUC
  is about 67 / 74 (AEM).
* RegulAR reports omission F1 0.76 against 0.32 for a baseline. This is a user study with 12 people on 2
  cooking tasks, not a benchmark.
* EgoErrorVQA, multiple choice over all types: best model 66.4 % against 85.9 % for humans.

Our numbers are not directly comparable. Ours are per type and from raw video. The published ones are
pooled over types, and our notes don't record whether they were given step segments.

## 3. Misordering

**Our result.** `procqc/direct/misorder.py` plus verifier v2; report `2026-09-29_misordering_check.md`.
* CaptainCook4D held-out (Tomato Chutney, published graph):
  * without verifier: 10 / 10 recordings, 0 / 5 false;
  * with verifier: 8 / 10 recordings, 0 / 5 false.
* CaptainCook4D development, without verifier: 9 / 12 recordings, 2 / 9 false.
* Event recall is low by construction: CaptainCook4D tags every step of an inverted block, and the check
  reports only the first.
* Order between the rounds of a repeat block, per object, on Assembly101: 1 / 23 caught. That rule covers
  only one way of getting the order wrong.
* The verifier loses more true flags than false ones it removes, so it is used only to rank the review
  queue.

**Works or may work.**
* Procedures with a stated dependency graph (published or written into the SOP).
* Steps that are each done once.

**Doesn't or may not.**
* Orders that are allowed but missing from the graph. One recipe in three needed the graph relaxed from
  correct recordings.
* A part put on before the part it rests on, when the SOP does not state that dependency (Assembly101).
* Internal SOPs list steps but rarely state which order is required.

**How hard the error type is.** Medium. The check itself is simple once the graph is right. The graph is
the hard part.

**How hard the data is.** Medium. CaptainCook4D has published graphs. Toy assembly and internal tasks
don't, and their order constraints come from the objects themselves.

**Published.**
* Differentiable Task Graph Learning on Assembly101-O: F1 75.9. This is online detection of procedural
  mistakes (order, omit, correction and repeat pooled).
* Graph learning on CaptainCook4D reaches graph F1 87.8.

These are pooled and use a different metric from ours.

## 4. Off-procedure addition

**Our result.** `procqc/direct/offgraph.py`; report `2026-10-01_offgraph_addition_check.md`.
* Synthetic: 20 / 20 caught, 0 / 20 false. All 20 were caught by the scene-change path, because every
  synthetic addition was spliced from another room.
* CaptainCook4D: 0 false flags on 36 recordings. It has no addition labels, so this tests false alarms only.
* A text probe of the same-room path caught 36 / 36. The same-room path has not been tested on video.

**Works or may work.**
* An action from another task or another place.
* Internal data, if the SOP lists the allowed incidental actions (the start/end gestures already are).

**Doesn't or may not.**
* An extra action that resembles a listed step. It gets matched to that step and slips through.
* Incidental actions such as wiping hands or fetching a tool. They need a policy, or they become false flags.

**How hard the error type is.** Hard. "Not in the procedure" has to be separated from style variation and
incidental actions.

**How hard the data is.** We have no real labelled set. Assembly101's "shouldn't have happened" undos were
filed under addition in our distribution notes; we used them as redundant repeats instead. EgoPER Step
Addition needs an e-mail request to its authors.

**Published.** Labelled by EgoPER (Step Addition), EgoErrorVQA ("Unintended and Unnecessary Action") and
Assembly101 (unnecessary detach). Our research notes hold no per-type detection number for it.

## 5. Redundant repeat (concluded 11 Oct 2026)

**Our result.** `procqc/direct/repeat.py` and `repeat_v2.py`; report `2026-10-01_repeat_check.md`.
* CaptainCook4D: 5 / 5 confirmed flags were real (a second egg, a second spoonful). They are reported as
  parameter deviations, because the step states an amount. Recall was limited: 3 labelled repeats were
  rejected because the narration was mis-timed.
* Synthetic: 1 / 18. The duplicated clips are 1.5–3 s long, and the narration merges them.
* Assembly101: 0 / 42. The verifier called most labelled repeats corrections.

**Works or may work.**
* A discrete repeat of a counted step (a second scoop, a second press).
* Internal round-based tasks, if the log keeps each object separate.

**Doesn't or may not.**
* Dense take-apart-and-refit work, where judging "unneeded" needs the build order.
* Long continuous actions, which the object log may split in two.

**How hard the error type is.** Hard. The check has to know that the first result was already achieved,
and that nothing made the redo necessary. Its boundary with a correction is a judgement: on Assembly101 our
verifier and the annotators disagreed on most cases. On the 9055 roof the frames showed the annotators
were wrong; on others the verifier invented a fault.

**How hard the data is.** Hard. Assembly101 has small parts and many undos, and its coarse labels have no
screw actions.

**Published.** No detection result. Only EPIC-Tent labels repeats (3 labels). EgoProceL reports a 0.49
repeated-step ratio as natural variation, not as errors.

## 6. Correction loop (concluded 11 Oct 2026)

**Our result.** `procqc/direct/correction.py`; report `2026-10-01_repeat_check.md`.
* Assembly101, rule v1: 22 / 44 caught, 22 false; precision 0.50, recall 0.50.
* Assembly101, rule v2 (a correction must change something): precision 0.67, recall 0.41, but repeat false
  flags rose from 7 to 10. Rule v2 was found on this same data, so it is not a held-out number.
* The disposition is tag and retain: an error segment when the first result was at fault, plus a recovery
  segment.

**Works or may work.**
* A part placed wrongly and then moved to the right place. A visible change happens while the part is off.

**Doesn't or may not.**
* Refitting the same part in the same place: a fix or not, the log can't tell.
* Small parts that the log misses or misnames.

**How hard the error type is.** Medium to hard. The undo is visible. Whether it fixed a fault is a
judgement.

**How hard the data is.** Hard on Assembly101, for the same reasons as repeat.

**Published.**
* Labelled by Assembly101 (6.7 % of coarse segments are corrections), EgoPER (Step Correction), HoloAssist
  (corrected by the performer) and EgoOops (self-correction).
* Robot-learning practice keeps recoveries for training: π0.7, AgiBot World, ReTVL.
* Our research notes hold no per-type detection number for corrections.

## 7. Wrong tool / object / ingredient

**Our result.** `procqc/direct/wrongtool*.py` (v1–v6); report `2026-10-01_wrong_tool_check.md`.
* v5 on 20 unseen recipes (held-out, run once): 16 / 24 recordings, 8 / 20 clean recordings flagged;
  events precision 0.45, recall 0.31. Not usable.
* v6's relation rule on v5's saved answers: 7 / 20 clean flagged; precision 0.51, recall 0.28. The test set
  had been looked at by then.
* Development (egg sandwich): 7 / 9 recordings, 0 / 4 false.

**Works or may work.**
* A coarse swap: a bowl for a ramekin, or bare hands for a knife.
* Internal pick-and-place, if the SOP names the objects and the allowed substitutes.

**Doesn't or may not.**
* Deciding whether two names are the same item (a variety, a synonym, a more specific name). This caused
  19 of 29 false flags.
* Look-alike ingredients, such as sugar for salt or baking soda for baking powder.
* Brief use of an item.
* Steps the check never looks at. Version 5 checks each item at only a few steps, and the substitution may
  happen at another one.
* Labels that can't be read at 360p, even cropped (vegetable against olive oil).

**Why the misses happen: free frame check (11 Oct 2026).** Six substitutions that version 5 missed on the
unseen recipes were picked so that seeing could be the problem. Each was checked on full frames, on a 3x
crop of the work area, and against version 5's saved answers.

| case | frames | why it was missed |
|---|---|---|
| knife instead of floss | knife clearly visible | step never checked |
| cheddar instead of parmesan | bag label readable in the full frame | step never checked |
| spoon instead of whisk | hand covers the utensil, also in the crop | step never checked |
| metal spatula instead of wooden spoon | the stirring is out of view | the moment of use was not found |
| vegetable oil instead of olive oil | label unreadable, also in the crop | 3 / 3 answers "cannot tell" |
| sugar instead of salt | white granules from a paper bag | 1 of 3 answers right; flagging needs 3 / 3 |

* Two views (a full frame plus a work-area crop) would have fixed none of the six. Version 5 already sends
  2 crops with its frames, so it is a two-view design already.
* The main cause is coverage: 3 of 6 steps were never checked. Version 6 checks every step and targets
  this; it has had only a 2-recording smoke test.
* Crops add detail only when the source has it. At 360p they don't; on internal data (1440x1080 per eye)
  they would.
* Our CaptainCook4D copy is video only. Sensor signals (grasp moments from hand joints) can be tried on
  internal data only.

**How hard the error type is.** Hard. It needs an equivalence policy (same item at any variety or synonym,
a different form, a different item), which a model judging case by case does not apply consistently.

**How hard the data is.** Hard. CaptainCook4D is 360p with small items, and its labels are inconsistent
across recordings of the same recipe.

**Published.**
* CaptainCook4D Preparation Error, zero-shot with reasoning: recall 51.7 (seen recipes) and 56.0 (unseen).
  Precision is not reported. After training (Qwen2.5-VL-7B with GRPO): 69.0 / 76.9.
* Plain zero-shot answers "correct" for nearly everything (F1 0).
* EgoPER Step Modification, zero-shot: about 42.7 on average.
* EgoOops: overall mAP@0.3 of 2.5.
* Robot failure detection (FailBench): best balanced accuracy 0.77.

Scored per step, as the post-training paper scores, our recall (0.29–0.44) is below its zero-shot recall
of 56.0. Our precision is higher: 0.37 against about 0.21, counted its way. See "Our checks in the
published protocols" below. Our false-alarm rate on clean recordings is the blocker, and the published work
does not report one.

## 8. Step parameter deviation

**Our result.** Only repeated additions are built ("2 eggs instead of 1", routed from the repeat check).
* CaptainCook4D development: 5 / 0 / 10 with the verifier.
* CaptainCook4D held-out: 0 of 2 caught, 0 false.
* Amount, time, temperature and technique deviations are not built. The agreed policy is to check only
  explicit counts and settings, and to send small amounts to a human.

**Works or may work.**
* Counted amounts and discrete settings.
* Durations, if sensor timestamps are used (internal data has them).

**Doesn't or may not.**
* Small or poured amounts, temperatures and force. These are not visible on video.

**How hard the error type is.** Hard. The SOP must state a measurable parameter, and the video must show it.

**How hard the data is.** Hard on video alone.

**Published.** This is the most common published type: 35 % of pooled labels (CaptainCook4D Measurement,
Timing, Temperature and Technique, plus EgoPER Slip and others). Per-type recall on step clips is in
"Published protocols checked" below; per-type precision is not published.


## 9. Gestural anchoring: recording start and end signal (added 12 Oct 2026)

Full report: `2026-10-13_gestural_anchoring_check.md` (rubric definitions, method, both test sets, frame review,
open items). Code: `procqc/signals/gesture_verify.py`.

**Our result.**
* Set A, 100 internal recordings that reviewers scored perfect: the sensor log alone passes 94 end and 85 start
  markers. The frame check (v2) leaves no false "signal missing". The 2 s timing rule marks 23 ends and 30 starts as
  medium, all against the reviewers.
* Set B, 70 internal recordings that reviewers flagged medium or discard:
  * Discard works: end 9 / 9 flagged, start 19 / 23 to discard or review, and 15 of our 16 discards agree.
  * Medium does not: the timing gap is no better than chance (AUC 0.63 end, 0.43 start). A frame review of 16 end
    misses found a long signal hold in 3, a small distant signal in 1, and nothing visible in 12.
* Cost: one frame call per flagged marker ($0.006); the goal time comes from the early-termination check.

**How hard the error type is.** Easy for discard (missing signal, unfinished task). Hard for medium: what reviewers
mark is mostly not visible at the boundary.

**How hard the data is.** Easy with head-mounted sensors.

**Published.** Nothing in our research notes.

---

## Comparability caveats

* Most published numbers are pooled over error types. Ours are per type.
* Our research notes do not record, for most published numbers, whether the method was given the
  annotators' step segments or started from raw video. Ours start from raw video. This has to be checked
  per paper before any comparison.
* Metrics differ: EDA, AUC and F1 at an IoU threshold, against our event matching by step and time plus a
  per-recording decision. No published number above is a like-for-like comparison.
* The published sets and ours are cooking and toy assembly. Nothing published, and nothing of ours, has
  been measured on internal household headset data.

---

## Published protocols checked (11 Oct 2026)

Three papers were read for their exact test setting: the CaptainCook4D paper, the post-training paper, and
Differentiable Task Graph Learning. Numbers are from their tables, read on arXiv HTML pages.

### CaptainCook4D (Peddi et al., NeurIPS 2024; arXiv 2312.14556)

* **Input:** the annotators' step segments, cut into 1 s pieces with a majority vote per step. Untrimmed
  video is not used.
* **Prediction:** error or normal per step.
* **Supervised, Table 2:** best F1 55.4 on the step split (Omnivore: P 51.6, R 59.8, AUC 75.7) and 56.0 on
  the recordings split (ImageBind).
* **Zero-shot video models, Table 3:** F1 41.8 (Video-LLaVA) and 46.1 (TimeChat), with one prompt per error
  category.
* **Zero-shot per category, Table 8:** P / R / F1. No split is stated.

| category | Video-LLaVA | TimeChat |
|---|---|---|
| Order | 16.3 / 35.3 / 22.3 | 17.2 / 6.3 / 9.2 |
| Missing step | 5.1 / 3.9 / 4.4 | 2.2 / 0.4 / (12.4 as printed, inconsistent) |
| Preparation | 7.7 / 12.3 / 9.5 | 7.1 / 50.1 / 12.4 |
| Measurement | 0.0 / 0.0 / 0.0 | 6.1 / 44.2 / 10.7 |
| Technique | 11.1 / 0.4 / 0.7 | 2.4 / 0.4 / 0.6 |
| Temperature | 0.5 / 4.6 / 0.9 | 0.6 / 6.2 / 1.2 |
| Timing | 6.6 / 0.6 / 1.1 | 3.0 / 17.6 / 5.1 |

### Post-training VLMs for video mistake detection (Spurio et al., 2026; arXiv 2608.28406)

* **Input:** one clip per step, cut at the annotators' start and end times. The step text is given, and
  the prompt lists the mistake types.
* **Prediction:** yes or no per clip. Mistakes are the positive class.
* **Types tested:** Technique, Preparation, Temperature, Measurement and Timing. Missing steps and order
  errors are excluded.
* **Test set:** CaptainCook4D seen recipes (484 normal, 107 error clips) and unseen recipes (459 normal,
  100 error clips). Which recipes are unseen is not listed.
* **Overall on unseen recipes, Table 2** (R / P / F1, model Qwen2.5-VL-7B):
  * zero-shot: 0 / 0 / 0 (answers "no" to everything);
  * zero-shot with reasoning: 54.8 / 20.6 / 29.9;
  * best trained: 80.0 / 22.8 / 35.5.
  Precision is about 20 % throughout, against a base rate of 18 % error clips. The false-positive rate
  is not reported.
* **Recall per type, unseen recipes, Table 3** (zero-shot with reasoning → best trained):

| type | zero-shot with reasoning | best trained |
|---|---|---|
| Preparation | 56.0 | 76.9 |
| Measurement | 63.3 | 96.9 |
| Timing | 65.0 | 75.0 |
| Technique | 26.1 | 71.4 |
| Temperature | 33.3 | 33.3 |

  No per-type precision is reported.

### Differentiable Task Graph Learning (Seminara et al., NeurIPS 2024; arXiv 2406.01486)

* **Task:** online mistake detection on Assembly101-O and EPIC-Tent-O (the PREGO benchmark). A step is a
  mistake when its preconditions in the learned graph were not seen earlier. This is the same rule as our
  misordering candidates.
* **Mistake types:** order, omission, correction and repetition, pooled. No per-type results.
* **Two input settings, Table 3:** the annotators' action sequences, or sequences predicted from video by
  an online action detector. Metric: average of the F1 of the "correct" and "mistake" classes.

| method | Assembly101-O, annotator sequences | Assembly101-O, predicted from video | EPIC-Tent-O, annotator | EPIC-Tent-O, predicted |
|---|---|---|---|---|
| DO (theirs) | 75.9 (mistake F1 61.6) | 53.5 (mistake F1 28.1) | 58.3 | 46.5 |
| TGT-text (theirs) | 62.8 | 53.0 | 64.1 | 43.8 |
| PREGO | 39.4 | 32.5 | 32.1 | 29.4 |

  Moving from annotator sequences to video costs 22 points on Assembly101-O. Their scoring code passes the
  predictions as sklearn's first argument, so the printed precision and recall are swapped (F1 is not
  affected): DO's mistake class on annotator sequences is precision 90.4, recall 46.7.
* **CaptainCook4D graph learning, Table 1:** F1 87.8 (DO).

### What this means for comparing

* Our omission and misordering rules on the annotators' own step sequences are not the same setting as
  CaptainCook4D Table 8. Our rule receives step names and order, which nearly gives away the answer for
  these two types; their models receive only the segments' video. The fair comparison for these two types
  is our raw-video result against their per-category zero-shot numbers, scored per step.
* Wrong tool / object and parameter deviation can be compared with the post-training paper's protocol
  (a step clip with the step text, yes or no). For wrong tool / object, our version 5 already uses
  annotator step timing.
* Misordering compares best with Differentiable Task Graph Learning: our rule on annotator sequences
  against their annotator-sequence setting, and our raw-video result against their predicted setting.
  This needs the Assembly101-O split from the PREGO repository.

---

## Our checks in the published protocols (11 Oct 2026)

Scored from saved runs and label files, no model calls. Code: `procqc/audit/per_step_scores.py` (CaptainCook4D,
per step) and `procqc/audit/assembly101_o.py` (Assembly101-O). Our recordings and splits are not the papers'
unless stated, so these are positions, not like-for-like results.

### CaptainCook4D, per step (the unit of CaptainCook4D Table 8 and the post-training paper)

A unit is one step of one recording: the annotated steps, plus missing steps, plus any step we flagged.

| type | our data | setting | P | R | F1 | published, same unit |
|---|---|---|---|---|---|---|
| Omission | held-out (Tomato Chutney, 15 recordings) | detector only | 0.61 | 0.74 | 0.67 | Missing step, zero-shot: F1 4.4 (Video-LLaVA) |
| | | with verifier | 0.92 | 0.58 | 0.71 | |
| | development (21) | detector only | 0.67 | 0.43 | 0.52 | |
| | | with verifier | 0.69 | 0.32 | 0.44 | |
| Misordering | held-out (15) | detector only | 0.75 | 0.13 | 0.21 | Order, zero-shot: F1 22.3 (Video-LLaVA), 9.2 (TimeChat) |
| | | with verifier | 0.90 | 0.09 | 0.17 | |
| | development (21) | detector only | 0.69 | 0.20 | 0.31 | |
| | | with verifier | 0.67 | 0.13 | 0.22 | |
| Preparation (wrong tool / object v5, annotator step times) | 20 unseen recipes (44) | detector only | 0.25 | 0.44 | 0.32 | Preparation recall on unseen recipes: 56.0 zero-shot with reasoning, 76.9 trained; F1 9.5–12.4 zero-shot (Table 8) |
| | | with verifier | 0.25 | 0.29 | 0.27 | |
| | | with verifier, only the step where the item was seen | 0.31 | 0.14 | 0.20 | |

* **Omission** is well above the published per-category number, but the settings differ. A missing step has
  no video of its own, and the paper does not say how its per-step models score one. Our check reasons over
  the whole recording against the step list.
* **Misordering** recall per step is low by construction. The labels tag every step of an inverted block,
  and the check reports only the first one. At recording level the same runs catch 10 of 10 held-out
  recordings.
* **Preparation**: our recall (0.29–0.44) is below the post-training paper's zero-shot recall (56.0).
  * A flag that lands on a step carrying any of that paper's five error types counts as right in its
    precision. On that basis ours is 0.37 (0.41 counting only the step where the item was seen), against
    about 0.21–0.23 there.
  * Our check looks only for substitutions, while their Preparation positives include soiled or unwashed
    items. Their unseen recipes are not listed, so the test sets differ.
* **Parameter deviation** (measurement, timing, technique, temperature): we have no check, so there is no
  number.

### Assembly101-O (PREGO benchmark; Differentiable Task Graph Learning, Table 3)

The protocol is rebuilt from the authors' code:
* there are 182 test sequences, each cut at its first mistake, giving 677 segments, 182 of them mistakes;
* the first mistakes are 82 unneeded detaches, 61 wrong orders and 39 wrong positions.

| setting | data | mistake P / R / F1 | average F1 | published |
|---|---|---|---|---|
| flag nothing | all 182 | – / 0 / 0 | **42.2** | PREGO 39.4, Count-Based 26.0 (annotator sequences) |
| our misordering rules, annotator sequences | all 182 | – / 0 / 0 | 42.2 | DO: mistake F1 61.6, average 75.9 |
| + our repeat rule | all 182 | 0.54 / 0.35 / 42.7 | 63.2 | TGT-text: mistake F1 55.7, average 62.8 |
| + our correction rule | all 182 | 0.50 / 0.66 / 57.0 | 68.8 | |
| from video, detector only | our 29 recordings in the test split | 0.27 / 0.34 / 30.3 | 50.2 | DO from video: mistake F1 28.1, average 53.5 |
| from video, with verifiers | our 29 recordings | 0.10 / 0.03 / 5.1 | 42.3 | |

* **Our misordering rules flag nothing here.** The general SOP has no part-level order, so the precondition
  rule has nothing to check. The published methods learn the part order from 135 training sequences. This
  is the real gap for misordering: our pipeline takes order only from the SOP.
* **The repeat and correction rules are not comparable to the published rows.** The benchmark is online:
  each step must be judged when it happens. Our rules use what happens later (the part put back, the first
  result undone), which the online methods cannot see. Those rows show what our rules find with hindsight,
  not where they stand against DO.
* **Average F1 rewards flagging nothing.** It averages the mistake class with the much larger correct
  class, so flagging nothing scores 42.2, above PREGO. Mistake F1 is the number to compare.
* **From video with verifiers, our checks are at the flag-nothing level** (mistake F1 5.1). This matches
  the repeat result on the same recordings: the verifiers call most undos fixes.
