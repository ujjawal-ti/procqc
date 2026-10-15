# Omission as its own check, and a benchmark of every verifier (30 Sep 2026)

Code: `procqc/direct/omission.py` (candidates + verifier v1), `procqc/audit/verifier_bench.py`
(benchmark). Runs: `out/omission_check/cc4d_v1`, `out/verifier_bench/`.

## Omission method

* **Candidates, no model**: a required step never seen in the narrated step sequence while a step
  that requires it (directly or through others) is seen. A missing final step, or a missing step
  with nothing after it done, is early termination and handled there.
* **Verifier v1, one video call**, three clips: the gap where the step belongs (at most the last
  120 s before the dependent step), the start of the first dependent step, the first 15 s. Questions
  by state: performed in the gap? result present when the dependent step begins? already present at
  the start? No / no / no confirms; performed, or result present, rejects (the latter noted as
  off-camera or pre-satisfied).
* Step sequence: the same cached narration and match stage as the misordering check.

## Data

CaptainCook4D, 36 recordings with video: 22 with omission labels (47 labels), 14 without.
Development recipes (egg sandwich, tuna wraps): 14 with / 7 without. Held-out (Tomato Chutney):
8 with / 7 without. Some labels name the final step (e.g. "secure the wrap"); by our definitions
that is early termination, so recall is also reported without them.

## Results

| | recordings with omission flagged | recordings without flagged | step TP / FP / FN | precision | recall (excl. final-step labels) |
|---|---|---|---|---|---|
| Oracle: rule on the annotators' own sequences (51 recordings) | 27 / 27 | 0 / 24 | 50 / 0 / 10 | 1.00 | 0.83 (0.93) |
| Dev, no verifier | 13 / 14 | 0 / 7 | 12 / 6 / 16 | 0.67 | 0.43 (0.52) |
| Dev, verifier v1 | 10 / 14 | 0 / 7 | 9 / 4 / 19 | 0.69 | 0.32 (0.39) |
| **Held-out, no verifier** | **7 / 8** | 2 / 7 | 14 / 9 / 5 | 0.61 | **0.74** |
| **Held-out, verifier v1** | 6 / 8 | **0 / 7** | 11 / 1 / 8 | **0.92** | 0.58 |

Cost $1.30 for the verification of all 36 (narration and matching cached); ~$0.03 per candidate.

Same 10 recordings as the earlier shared pipeline: that pipeline found 6 of 8 omissions (6 / 2 / 2);
this module 3 / 4 / 5 without the verifier. **The loss is in step matching, not in the rule or the
verifier** (the oracle finds 50 of 60 with no false alarm):
* 28_26: the empty lettuce leaves were rolled and pinned; the matcher did not count an incomplete
  "roll up the wraps" as that step, so nothing after the missing fillings looked done, and they were
  read as an unfinished tail. The earlier judge reasoned past this.
* 1_10, 1_28: beating the egg (the annotators' "stir the ramekin") was not matched as stirring, so the
  look-alike rule picked the wrong microwave step.
The earlier narrator saw the step list and labelled steps itself, which helps omission and hurts
misordering (it tells swapped steps in the written order). Next step: a second version of the match
stage (degraded or synonymous performances count as the step), measured on both checks.

## Verifier benchmark

For every candidate: is it a real error, and did the verifier keep it, send it to review, or reject it?
The shared adjudicator (narrate arms) turns a rejection of a confident detection into review
("disagree, don't discard"), so for it "rejected" is rare and its effect shows in review counts.

| verifier | set | true candidates: kept / review / rejected | false candidates: kept / review / rejected | precision before → after | step recall before → after (filter) | net (false removed − true lost) | cost |
|---|---|---|---|---|---|---|---|
| misordering v1 | dev | 3 / 0 / 6 | 1 / 0 / 3 | 0.69 → 0.75 | 0.20 → 0.07 | −3 | $0.15 |
| misordering v2 | dev | 6 / 1 / 2 | 3 / 1 / 0 | 0.69 → 0.67 | 0.20 → 0.13 | −2 | $0.47 |
| misordering v1 | held-out | 8 / 0 / 4 | 2 / 0 / 2 | 0.75 → 0.80 | 0.13 → 0.08 | −2 | $0.28 |
| misordering v2 | held-out | 9 / 0 / 3 | 1 / 1 / 2 | 0.75 → 0.90 | 0.13 → 0.09 | −1 | $0.41 |
| omission v1 | dev | 9 / 1 / 2 | 4 / 0 / 2 | 0.67 → 0.69 | 0.43 → 0.32 | 0 | $0.61 |
| **omission v1** | **held-out** | 11 / 0 / 3 | **1 / 0 / 8** | 0.61 → **0.92** | 0.74 → 0.58 | **+5** | $0.69 |
| shared adjudicator | CC4D, 10 rec. (all kinds) | 9 / 2 / 0 | **6 / 1 / 0** | 0.61 → 0.60 | 0.32 → 0.27 | 0 | $0.36 |
| shared adjudicator | CC4D, fix round 1 | 5 / 0 / 4 | 6 / 1 / 0 | 0.56 → 0.46 | 0.27 → 0.15 | −4 | $0.33 |
| shared adjudicator | synthetic, fix round 1 | 6 / 1 / 0 | 8 / 21 / 2 | 0.18 → 0.43 | 0.47 → 0.40 | +2 | $0.72 |

Caveat on "false": several are label disagreements rather than verifier errors. The look-alike
microwave steps are named differently by the annotators (1_10, 1_36, 1_136); 15_41 (mustard seeds
never added, verified in the clip) has no omission label; 15_28's garlic may have been pre-peeled
(frames inconclusive).

## Recommendation

* **Shared adjudicator: retire it.** On real data it kept 6 of 7 false candidates and removed none;
  its only effect is sending more items to review. Replace it with per-kind verifiers.
* **Misordering verifiers: do not use them as a filter.** Net negative on both sets (they lose more
  true detections than false ones they remove). Either drop them (saves ~$0.03 per candidate) or use
  them only to order the review queue.
* **Omission verifier v1: keep, as a router.** On the held-out recipe it removed 8 of 9 false
  candidates (precision 0.61 → 0.92) but lost 3 of 14 true ones, so route its rejections to human
  review instead of discarding them: recall stays at the no-verifier level and reviewers can skip the
  ~50 % it confirms. On the development recipes it was neutral (net 0).
* In general a verifier earns its place only where the detector produces many false candidates;
  where the detector is already precise (misordering on real data), it can only lose recall.

## Match stage v2 (30 Sep 2026): no measurable gain

`procqc/direct/match_v2.py`, selected with `--match v2` (v1 stays the default). A step counts as
performed when its action reaches its object even if degraded or under a synonym; the difference is
recorded as `deviation`. Same 36 recordings, cached narrations; $0.78 (omission run) + $0.15
(misordering run).

| | match v1 | match v2 |
|---|---|---|
| omission, dev, no verifier: recordings / step TP-FP-FN | 13/14, 12/6/16 | 13/14, 12/7/16 |
| omission, held-out, verifier v1 | 6/8, 11/1/8 | 6/8, 12/1/7 |
| misordering, dev, verifier v2: recordings | 7/12 | 6/12 |
| misordering, held-out, verifier v2: recordings | 8/10 | 7/10 |

Why the three target recordings did not change:
* 28_26: the narration itself never mentions rolling or pinning the wraps (it ends with taking out
  the toothpicks), so no matcher can find them. A narration miss.
* 1_10, 1_28: the narration does say "stir egg in ramekin cup", but both matchers refuse it **by
  order**, against their own first rule: "beating egg before cooking; step 4 is stirring after
  microwaving". The procedure context the matcher receives lists steps in order with their
  prerequisites, and it reasons from that. Whether beating a raw egg is the recipe's "stir" is also a
  labelling convention (the annotators say yes).

Decision: keep match v1 as the default. Changing the matching rules does not help; the remaining
omission misses are a narration miss and a matcher that reasons from the written order.
