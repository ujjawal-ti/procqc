# AutoQC smoke test on the synthetic Lightwheel set, 24 Sep 2026

15 episodes from `out/synth_lightwheel/manifest_smoke.jsonl`: 3 per injected kind (omission, early
termination, repeat, misordering, off-graph insert), no clean episodes. Scoring with
`procqc.audit.cli metrics` against `labels.jsonl`; strict = confirmed findings only, lenient adds
findings routed to a human. Kind aliases (`offcamera_step`→omission, `goal_unmet`→early termination)
and early-termination-by-kind matching apply to every arm.

## Arms

| arm | how detection works | detection model | adjudication |
|---|---|---|---|
| pipeline v1 | motion proposals → VLM step scorer (3 frames/window) → beam decode → refine → symbolic verify → reconcile | gemini-3.8-flash via Fuelix, frames | same 3-stage adjudicator (Fuelix) |
| pipeline v2 | v1 + four fixes: unknown segments become off-graph candidates; chain graph has a mandatory terminal step and expected durations; omission of a step shorter than the 0.9 s floor is needs_review; termination matched by kind | same | same |
| direct (kinds) | one native-video call per taxonomy kind with the step list, that kind's definition and boundary rules (`procqc/direct/arm.py`); omissions after the termination point folded into the termination; informational findings not adjudicated | gemini-3.8-flash via Google AI Studio, 5 fps video | same |

## Per kind, strict (TP / FP / FN of 3 injected each)

| kind | pipeline v1 | pipeline v2 | direct (kinds) |
|---|---|---|---|
| omission | 0 / 27 / 3 | 0 / 16 / 3 | 0 / 2 / 3 |
| early termination | 0 / 0 / 3 | 1 / 2 / 2 | **3** / 2 / 0 |
| addition (repeat) | 0 / 1 / 3 | 0 / 1 / 3 | 0 / 0 / 3 |
| misordering | 0 / 2 / 3 | 0 / 2 / 3 | 1 / 1 / 2 |
| addition (off-graph) | 0 / 0 / 3 | 1 / 0 / 2 | **3** / 2 / 0 |
| **all** | 0 / 30 / 15 | 2 / 21 / 13 | **7** / 7 / 8 |

## Episode level

| | pipeline v1 | pipeline v2 | direct (kinds) |
|---|---|---|---|
| micro precision / recall (strict) | 0.00 / 0.00 | 0.09 / 0.13 | 0.50 / 0.47 |
| micro precision / recall (lenient) | 0.00 / 0.00 | 0.06 / 0.13 | 0.44 / 0.53 |
| verdict accuracy (flagged when not clean) | 0.80 | 0.73 | 0.67 |
| routed to human | 47 % | 53 % | 7 % |
| precision of findings at confidence ≥ 0.85 | 0.00 | 0.15 | 0.40 |
| cost, 15 episodes | $6.00 | $0.54 (cache) | $2.50 |
| cost per episode (uncached) | $0.40 | ≈ $0.40 | $0.17 ($0.13 video + $0.03 adjudication) |
| video tokens per episode | — | — | 115 k prompt tokens (5 fps) |

## What each arm actually did

**Pipeline.** The localizer misses the sub-second steps of these 15–33 step graphs; every missed
step becomes a symbolic omission and the adjudicator, shown six frames from the "expected window",
confirms most of them at 0.85–0.95. Swapped steps were never localized, so no order violation could
fire. Off-graph inserts were dropped with the "unknown" label before verification (fixed in v2, one
caught). Repeats were found by the decoder but rejected by the adjudicator. Two terminations were
reported in substance as omissions of the exact missing steps (fixed in v2 via the terminal step).

**Direct.** Early termination 3/3 and off-graph insert 3/3 with confidence 0.95–0.99 and correct
timestamps (within 0.1 s of the splice). Misordering 1/3: one caught exactly, one flagged on the
neighbouring step of the swapped unit and rejected by the adjudicator, one missed. Omission 0/3
strict: one found but escalated to human (lenient 1/3), two missed because the omitted unit's effect
(stamp pad on the table, tissues out of the bag) is visible later and the model reasoned the step
must have happened. Repeat 0/3: the model described one repeat correctly ("nozzle detached and
re-inserted") and the adjudicator rejected it; a duplicated 26 s coiling clip was read as
"unwinds and re-coils" and reported as an off-graph action.

False findings of the direct arm after folding (7): "stand up" reported missing, as omission and
as termination, in two videos (`1a08eacf`, `eb7d161e`) whose GT places a 1–1.5 s stand-up in the
last 2–4 s of the recording, so these are model misses of a brief final action, not label errors; a
wire handle being mounted in `d0646d89` reported as off-graph in both variants of that source,
which is a real unannotated action in the recording rather than a model error; one stamp-pad
adjustment read as off-graph; one misordering flagged on the neighbouring step of a swapped unit.
Metric rule added on this run: an episode terminates once, so further early-termination predictions
in the same episode are not counted (applies to every arm; the pipeline's numbers did not change).

## Reading

1. On this fine-grained data, one graph-grounded video call per kind detects more, with fewer false
   findings, and costs less than the decomposed pipeline: 7 vs 2 true of 15, 7 vs 21 false,
   $0.17 vs $0.40 per episode, 7 % vs 53 % sent to a human.
2. Both arms fail on the same two kinds, omission and repeat, and for the same reason: judging them
   needs the object state before and after the step, not just the sequence. The adjudicator is
   currently the weakest link there (it rejected two true repeats and confirmed many false omissions).
3. The direct arm's weaknesses are exactly the pipeline's strengths: it has no step timeline, so
   there are no segment tags for tag-and-retain, and the adjudicator has only the model's own
   timestamps to pick frames from. A hybrid (direct kind calls for detection, localizer only
   around findings for timestamps) is the natural next arm.
4. 15 episodes is a smoke test. Per-kind numbers have wide intervals; the full run decides.

## Update after group 3/4 fixes (same 15 episodes)

Fixes: adjudicator packets built from the detector's own spans plus a context span the detector
returns (first occurrence for repeats, later prerequisite for misordering, neighbours of a gap for
omission); honest "symbolic verifier not run" text in the direct arm; disagree-don't-discard (a
detection asserted at >= 0.9 that the adjudicator rejects goes to a human, keeping its kind);
misordering labels accept any step of the moved unit. Direct arm re-called the video model
($2.12 + $1.28 across a 503 interruption); pipeline replayed from cache.

| kind (3 injected each) | direct v2 strict TP/FP | **direct v3 strict TP/FP** | **direct v3 lenient TP/FP** | pipeline v3 strict TP/FP |
|---|---|---|---|---|
| omission | 0 / 2 | 1 / 2 | 1 / 5 | 0 / 16 |
| early termination | 3 / 2 | 3 / 2 | 3 / 2 | 1 / 2 |
| addition (repeat) | 0 / 0 | 0 / 0 | **2** / 0 | 0 / 1 |
| misordering | 1 / 1 | 1 / 1 | 1 / 2 | 0 / 2 |
| addition (off-graph) | 3 / 2 | 2 / 2 | 3 / 3 | 1 / 0 |
| **all** | 7 / 7 | 7 / 7 | **10 / 12** | 2 / 21 |
| micro P / R | 0.50 / 0.47 | 0.50 / 0.47 | 0.45 / 0.67 | 0.09 / 0.13 |
| routed to human | 7 % | 40 % | 40 % | 53 % |

Detector alone (direct v3, before adjudication): 9 true / 12 false. What changed: the two true
repeats the adjudicator used to reject now survive as human-review items (the context span shows
the first occurrence, and the disagreement policy keeps them); the scissors omission is now
confirmed (packet frames from the detector's window instead of an empty expected window); the
makeup-case misordering still misses because the model named no finding this time. Cost of the
policy: the human review rate rises from 7 % to 40 %, which is the intended trade until per-kind
calibration exists. The pipeline arm is unchanged: its rejected true repeat was asserted at 0.7,
below the policy threshold.
