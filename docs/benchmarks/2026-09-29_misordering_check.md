# Misordering as its own check (29 Sep 2026)

Second module of the hybrid design. Code: `procqc/direct/misorder.py` (candidates + verifier v1),
`procqc/direct/misorder_verify_v2.py` (verifier v2), `procqc/graph/relax.py` (graph relaxation).

## Method, and where it comes from

The approach follows what our earlier research collected (docs/Validation_Report_and_Agentic_Pipeline.md):
a symbolic graph check proposes, a model verifies ("symbolic first, LLM second").

1. **Step sequence**: narration of the whole video (narrator sees no step ids or order), then the
   content-based match stage (`narrate_judge.match_narration`).
2. **Candidates, no model**: a step whose required prerequisite is performed only later. This is the
   precondition rule of Differentiable Task Graph Learning (Seminara et al., NeurIPS 2024;
   Assembly101-O F1 75.9) and RegulAR's executable-set check. A prerequisite never performed is an
   omission, not a misordering. Only the first inversion is reported (PREGO benchmark convention).
3. **Verification, one video call per candidate** on two clips (the step, the later prerequisite).
   * v1: clips of the narrated entry +5 s / +2 s; asks whether S is seen in clip 1, R seen in clip 2,
     R's result already present before S.
   * v2 (separate module, v1 unchanged): clips padded by half the step's typical duration from
     correct performances (5-45 s); asks by object state: S performed in clip 1, R's result absent at
     that moment, R's result present by the end of clip 2.
4. **Graph**: the published CaptainCook4D DAG, optionally relaxed to the orders seen in correct
   performances (every implied ordering kept only if all recordings without an Order Error tag
   respect it; leave one out, so a recording never relaxes its own graph).

## Data

CaptainCook4D, the two recipes with built graphs (Microwave Egg Sandwich, Spicy Tuna Avocado Wraps):
36 recordings in the annotations; 21 with video (11 downloaded for this test, gopro 360p, ~0.8 GB):
**12 with order-error labels** (46 labels; annotators tag every displaced step, up to 7 per recording)
and 9 without (4 fully clean). The synthetic Lightwheel swaps were dropped as a benchmark: swaps of
independent steps are not errors under a real procedure, and swaps of dependent steps produce
physically impossible footage (stapling with an open stapler) that no real recording contains.

## Results

Recording level = the QC decision (does a recording with an order error get flagged; does one
without get flagged). Step level = the flagged step equals an annotated one.

| | order-error recordings flagged (of 12) | others falsely flagged (of 9 / 24) | step level TP / FP / FN |
|---|---|---|---|
| **Oracle**: rule on the annotators' own step sequences, published graph | 11 (10 on the tagged step) | 1 of 24 | 11 / 2 / 35 |
| Oracle, relaxed graph | same | same | same |
| Candidates from the narration | 9 | 2 of 9 | 9 / 4 / 37 |
| **+ verifier v1** | 3 | 0 of 9 | 3 / 1 / 43 |
| **+ verifier v2** | **7** (8 incl. review) | 1 of 9 (2 incl. review) | 6 / 3 / 40 |

Earlier versions on the one order error available then (1_32): none found it.

Cost and latency (21 recordings, 6-18 min each): narration and match about $0.10 per new
recording; verification v1 $0.15 total, v2 $0.47 total (~$0.04 per candidate, longer clips);
end-to-end p50 115 s (v1) / 159 s (v2) per recording.

## What the numbers show

* **The rule and the graph are not the problem.** With perfect step sequences the rule flags 11 of
  12 recordings. The published graphs already match correct performances: relaxation dropped no
  ordering for the tuna wraps (76 of 76 kept) and one of 50 for the sandwich; results unchanged.
* **The narration's step order is good enough on real data**: 9 of 12 recordings get a candidate
  (oracle 11). The synthetic swaps failed because 1-5 s spliced actions are below what a whole-video
  narration resolves; real CaptainCook4D steps last 30-70 s.
* **Verifier v1 was the bottleneck** (rejected 6 of 9 true candidates): clips too narrow for long
  steps, and it demanded to see the prerequisite action even when its result was already present.
  v2 fixes both: 7 of 12.

## Remaining failures (checked on the annotations or frames)

* 1_32 (missed by every version, including the oracle): the annotated step order is correct; the
  error is inside a step (lettuce removed, egg placed, lettuce put on top). Not visible in step order.
* 28_38, 28_44 (missed): no candidate; the narration did not reproduce the inversion.
* 1_49, 1_42 (v2 rejected / review): the misordering changed the step itself (egg placed on the bare
  board with the lettuce on top; the coating replaced by oil poured into the egg), so "was S
  performed" is answered no. Boundary with technique / preparation errors.
* 28_25 (v2 false alarm): the bowl was mixed at 850-862 s before the pepper (frames), then mixed again
  at 925-932 s. The narration missed the first mixing and matched the re-mix; at the pepper moment the
  bowl looks unmixed, so v2 confirmed. A repeated step, not a verifier problem.
* 1_143: flagged for cheese before salsa, which the graph forbids and the annotators did not tag; the
  tagged error ("egg poured before coating") has no coating at all, an omission by our definitions.
  A possible annotation miss, useful for annotator QC.

## Held-out test: Tomato Chutney (29 Sep 2026)

Run once, no change to any component after seeing the results. 15 recordings (10 with order errors,
96 order-error labels; 5 fully clean), ~3 GB of video, $2.87 for all four runs (narration $1.60,
match $0.40, verification v1 $0.37 / v2 $0.47).

Oracle first (annotators' own step sequences): the published graph flags all 10 order-error recordings
but also **4 of the 5 clean ones**; the leave-one-out relaxation (built before this recipe was seen)
drops 2 of 163 implied orderings that correct performances violate ("take the pan off the heat before
transferring to the serving bowl", 2 of 4; "salt before mixing in the tomato puree", 1 of 4) and cuts
that to 1 of 5, with all 10 still found. Unlike the two development recipes, this graph is stricter than
how the dish is correctly made.

On video (narration → candidates → verification):

| graph | verifier | order-error recordings flagged | clean recordings flagged | step level TP / FP / FN |
|---|---|---|---|---|
| published | **none** | **10 / 10** | **0 / 5** | 12 / 4 / 84 |
| published | v1 | 6 / 10 | 0 / 5 | 8 / 2 / 88 |
| published | v2 | 8 / 10 | 0 / 5 | 9 / 1 / 87 |
| relaxed | **none** | **10 / 10** | **0 / 5** | 11 / 2 / 85 |
| relaxed | v1 | 7 / 10 | 0 / 5 | 8 / 1 / 88 |
| relaxed | v2 | 8 / 10 | 0 / 5 | 9 / 1 / 87 |

Latency p50 ~230-300 s per recording (12-20 min videos), dominated by narration.

## Both test sets together (22 order-error recordings, 14 without)

| | flagged | falsely flagged |
|---|---|---|
| candidates, no verifier | 19 / 22 | 2 / 14 |
| + verifier v1 | 9 / 22 (published graph) | 0 / 14 |
| + verifier v2 | 15 / 22 | 1 / 14 |

## Conclusions

* The ordering rule on the narrated sequence is the detector; it generalized to an unseen recipe
  (10 of 10, no false alarm on the clean recordings).
* The verifier removes more true detections than false ones. On the held-out recipe there were no
  false candidates to remove, and v2 rejected 2 true ones; its questions treat a changed or partial
  step as "not performed" (15_39: "only one tablespoon of oil, a partial action"; 15_28; and on the
  development set 1_49, 1_42), which conflates misordering with parameter and technique errors.
* Recommended use: raise every candidate as a misordering flag; use the verifier's answer as a
  confidence and routing signal (confirmed → auto-flag; rejected → human review, not discard), in
  line with the disagree-don't-discard policy. Relax the graph from correct performances before
  deployment: it mattered for one recipe in three and costs nothing.
* v2 was tuned on the development recordings; its held-out result (8 of 10, 0 false) is the
  unbiased number.

Incident during the held-out runs: two runs in parallel wrote the same clip file at once and one sent
a half-written clip (HTTP 400). `termination.cut_clip` now writes to a temporary name and renames it
when complete. All cached clips were then deleted by a faulty integrity check (ffprobe is not
installed); clips are derived files and re-cutting is byte-identical, so no result or cache entry was
affected.
