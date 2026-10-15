# Pipeline optimization notes

Living document. Everything here is a candidate change, measured against the audit metrics
(`python -m procqc.audit.cli metrics`) and the per-stage cost tables (`verdict["cost"]`,
`run_summary.json`). Nothing in this file is applied unless it is also in the code and the README.

## 1. Cost baseline (2026-09-22/23, gemini-3.8-flash via Fuelix, 3 frames/window, 512 px)

Hair-dryer episode, 53 s, 6 steps, one run each configuration:

| Stage | Calls | Prompt tok | Compl tok | Reasoning tok | USD | Share |
|---|---|---|---|---|---|---|
| localize (≈15 windows) | 19 | 78,654 | 6,813 | 5,038 | 0.085 | 50% |
| refine (≈6 joins, 8 frames each) | 6 | ≈50,000 | ≈4,000 | ≈3,000 | ≈0.05 | 30% |
| effects (7 calls) | 7 | 29,362 | 4,861 | 3,174 | 0.040 | 24% |
| adjudicate (2 findings) | 9 | 31,700 | 5,065 | 3,792 | 0.043 | 25% |
| **total with refine** | ≈41 | ≈190,000 | ≈21,000 | ≈15,000 | **≈0.22** | |

Shares are of the no-refine total; with refine on, the total is about $0.27 per 53 s episode.
Observations:
* Prompt tokens are ~90% images (≈1.1k tokens per 512 px frame on this model).
* Reasoning tokens are ~75% of completion tokens: the model "thinks" ~300 tokens per window.
* Cached calls cost nothing; the cache key includes the frames, so reruns on the same video with
  unchanged prompts are free, but any prompt edit invalidates the whole stage.

## 2. Levers, cheapest first

| Lever | Expected saving | Risk | Status |
|---|---|---|---|
| Frames at 384 px instead of 512 | ~40% of image tokens | small objects (tips, caps) less legible | not tried |
| 2 frames/window for long steady steps (coil cord: 13 windows) | 20–30% of localize | direction ambiguity rises | not tried |
| Skip refine on joins where both neighbours are ≥0.9 confident and window edge is an activity minimum | 30–50% of refine | boundary error creeps back | not tried |
| Reasoning effort "low" for scorer/checker (if Fuelix passes `reasoning_effort`) | ~60% of completion tokens | unknown accuracy effect | check API support |
| Batch API / off-peak for offline QC | 50% list price on most providers | latency hours | not applicable via Fuelix? check |
| Cheaper scorer model (Flash-Lite class) with the same prompts | 3× on localize | recall on subtle steps | measure on audit set |
| Tracking/proprio boundaries instead of frame-diff | fewer, better windows; refine often unnecessary | needs sensor stream | free when data has it |
| **Binary decision heads (laya-vision post-training)** | 100–1000× on bulk tiers | needs labels; see §3 | planned |

## 3. Post-training plan: calibrated binary heads (laya-vision pattern)

Reference: github.com/r33drichards/laya-vision — SmolVLM-256M fine-tuned to emit a typed decision
(`choice` / `score`) in one forward pass, no text generation, trained with a proper scoring rule
and temperature-calibrated (ECE 0.124 → 0.034), 71 ms per image on an L4. Weights are CC BY-NC
(ScienceQA data); the recipe and Modal deploy scripts are Apache 2.0. We train our own heads.

### 3.1 Why binary questions

Every big prompt in the pipeline is a bundle of small perceptual questions plus reasoning glue.
The glue (which candidates to consider, how to combine answers, which rule applies) is already
deterministic code or the adjudicator. The perceptual questions are binary or small-choice and
per frame or per short window. That is the EgoErrorVQA framing: procedural-error understanding
posed as many short VQA items with a fixed answer set, evaluated with EDA/AUC, rather than one
open-ended judgement. Binary items are also what a 256M head can learn and calibrate.

### 3.2 Decomposition of the current prompts

| Current call | Binary / small-choice items it contains | Granularity |
|---|---|---|
| Step scorer (window → probs over candidates) | "Are hands/gripper in contact with a step object?" (background vs step); for each candidate step S: "Does this window show S?"; for mirror pairs: "Is <state> true in the FIRST frame?" / "...in the LAST frame?" | per window; the mirror items per frame |
| Boundary judge (8 frames → index) | for each frame k: "Has the NEXT step's start convention been met by frame k?" → boundary = first k with yes (monotone) | per frame |
| Predicate checker (before/after → truth per predicate) | for each predicate P and frame set: "Is <object> visible?" then "Is P true?" | per frame set (2–3 frames) |
| Effect-frame selection (AEM) | "Does this frame show the post-state of S?" (relevance) + Laplacian sharpness (already free) | per frame |
| Adjudicator narrate | free text — stays generative (frontier), tail only | per finding |
| Adjudicator classify/advocate | text-only reasoning — stays frontier, tail only | per finding |

Items in the first four rows cover >90% of today's calls and cost. All are answerable by a
calibrated head; only the adjudicator needs generation.

### 3.3 Training data we can collect now (log everything)

For every binary item the pipeline answers today, store: episode id, task id, item type, question
text (templated), frame ids/times, the frontier model's answer and confidence, and later the human
label from the audit (`labels.jsonl`) and the adjudicator's final status. This turns every QC run
into a labelled VQA corpus:

* frontier answers → weak labels (distillation), filtered by adjudication outcome;
* human audit labels → gold for the items touched by findings;
* synthetic injection → items with known ground truth (truncation, repeats) for free;
* the PIE-V approach (edit-consistent error synthesis) for kinds re-cutting cannot fake.

Target ~50k items per client task family before training a head; laya trained 72k items in 33 min
on an A100.

### 3.3a What the training side actually consumes (researched 2026-09-23)

**TypeSafe Jev** (the API Laya is compatible with): `POST /v1/systemone` with `{"state": <text|json>,
"questions": {name: {"type": "noul"|"choice"|"score", "instructions": str, "criteria": ...}}}`; answers carry
`noul` = P(true), `choice` + `probabilities` + `confidence`, `score` + `probabilities` + `legend`.
Text-only ("No image, audio, or video input"), no fine-tuning or data upload, $0.042/M input tokens,
70–500 ms. So Jev itself cannot be our student for frames; its *question contract* is what we adopt.

**Laya** (Convai, Apache-2.0, 421M ModernBERT text encoder): same wire protocol; RLCD objective =
REINFORCE with Gaussian-noised logits against strictly proper scoring rules (log + spherical, ranked
probability score for `score`) plus soft cross-entropy against the teacher distribution; per-type
temperature calibration (ECE 0.466 → 0.081 on typed-decisions). Its training set `LocalLLaMA/typed-decisions`
stores `state`, `questions`, `gold` (teacher `probabilities` averaged over 3 samples at T=0.7),
`label_agreement` (argmax agreement, total variation) — i.e. **soft teacher targets with agreement
statistics**, which is the pattern we replicate.

**laya-vision** (SmolVLM-256M fork; also ModernVBERT-250M and SmolVLM2 split-1024 checkpoints):
training record = `{"id", "image"|"images", "state_text", "question": {type, instructions, criteria},
"label", "target"?}`; `target` = probability per option in criteria order (soft CE); options are
**shuffled per example** so no positional bias; ≤2 images per record in its data (NLVR2 pairs, Atari
prev/current); 512-px tile = 64 tokens; `criteria` options cut to 48 tokens, question head 256 tokens;
`score` levels ≤14 words; class balance: no level above 3× the median level count in train; calibration =
per-type temperature by golden-section search on NLL, group-disjoint 5-fold (group_key = image id),
95% group-bootstrap CI, saved JSON with `temperatures`, `sources`, `fitted_on`, `evidence`. Note: the
fetched `vlm_train.py` implements soft CE (no RL term) despite the README; irrelevant for our data.

**Alternative students and their SFT formats** (all generative unless a head is added):
SmolVLM/SmolVLM2 → HF `messages` with `{"type":"image"}` blocks + `images` list; Qwen2.5/3-VL →
`{"image": [...], "conversations": [{"from":"human","value":"<image>\n..."}]}` (LLaMA-Factory ShareGPT
equivalent); Florence-2 → task-prefix + answer string, single image; PaliGemma → `prefix`/`suffix`;
Moondream → hosted SFT API only; ModernVBERT → bidirectional encoder, `[MASK]`-marker readout (what
laya-vision's ModernVBERT checkpoint does), the natural classification-head backbone.

**Consequences for `procqc/itemlog/export.py`:** canonical record = laya-vision record + `group_key`
(episode) + `provenance` (teacher model, prompt version, label source/weight, n_samples). Item mapping:
`window_active`, `predicate_visible`, `boundary_reached` → `noul`; `predicate_truth` → `noul` where
visible (3-way `choice` optional); step presence → one `choice` per window over the presented steps +
background/unknown with the teacher's probability vector as `target`; `boundary_index` → `choice` over
frame indices only within the image budget. Converters: `laya` (native), `messages` (SmolVLM/Qwen),
`cauldron`, `jev` (text part only). Train-split balancing caps the majority label (binary: relative to
the minority; multi-class: 3× median, as laya). Splits and calibration folds are by episode.

### 3.4 Head design

* Backbone: SmolVLM-256M or Qwen3-VL-2B (Apache 2.0), frozen or LoRA.
* Input: 1–3 frames + templated question (object names from the graph, no free text).
* Output: typed `choice` over a fixed answer set (yes / no / not_visible), or `score` in [0,1].
* Loss: proper scoring rule (log loss / Brier) so the score is a probability; temperature scaling
  on a held-out split; report ECE and AUC per item type.
* Serving: L4, batched; expected ≈70–100 ms per frame, ≈$0.0003 per episode for all bulk items.
* The frontier model remains the teacher, the adjudicator on the tail, and the audit judge.

### 3.5 What the pipeline needs to change

1. An `ItemLog` writer in `llm_client`/scorer/checker: one JSONL line per binary item (§3.3).
2. A `HeadScorer` / `HeadPredicateChecker` implementing the existing `StepScorer` /
   `PredicateChecker` protocols, backed by the trained head; the registry chooses head vs frontier
   per item type with a confidence floor that falls back to the frontier when the head is unsure.
3. The router thresholds move to *calibrated* confidences (per-stage isotonic maps from the audit).
4. Evaluation: per item type AUC/EDA/ECE on the audit gold; per pipeline stage F1 and clean-FPR
   must not regress when a head replaces the frontier (validation gating, as for graph edits).

## 4a. Incident 2026-09-23: a 0.95 false positive skipped adjudication

Candies episode, second put-down: the effect checker reported `InBasket(candies)=False` after the
step at confidence 0.95 (rubric run; 0.75 in the earlier run). The router only adjudicated confirmed
findings below 0.9, so the finding went straight into the verdict. Re-adjudicating it offline: REJECT,
"Repeated objects" rule, rationale names the confusion between the placed bunch and the remaining
bunch, cost $0.007. Changes: `RouterConfig.adjudicate_all_confirmed=True` (confidence is never a
reason to skip adjudication until calibration maps exist), `effect_unmet` added to the always list,
and the effect checker now gets a `repeat_note` for steps with `permitted_repeats>1` or a CORRECTS
cycle ("judge the instance handled in this segment").

Why a human sees it and the checker did not: the human uses (1) the temporal sequence (the release
into the basket happens inside the segment, 17.9–19.2 s), (2) object identity (the bunch just carried
vs. the bunch still on the table), (3) task semantics (three cycles are expected, so leftover candies
are normal). The checker sees two frames before and two after, is asked a static state question with
a generic object noun, and has no cycle semantics. The adjudicator has all three (during-frames,
narration, local subgraph with `permitted_repeats` and the CORRECTS edge, the repeated-objects rule),
which is why it gets it right. Structural fixes beyond the repeat_note: instance-specific predicates
in graphs for repeated steps (e.g. `InBasket(candies_batch_k)`) or goal-only checks for cumulative
states; in the binary-head decomposition, a "was the carried object released into <container>?" item
over during+after frames replaces the static state item for transfer steps.

**Resolution (same day): general rules, no per-task edits.** `Predicate.scope` (instance / cumulative /
global) inferred from graph structure (`ops.infer_scope`: effects and preconditions of repeated steps →
instance, goals → cumulative); transfer detection from effect names/values (`ops.transfer_of`: a hold
predicate turning False + a placement predicate turning True); transfer steps are verified as a
transition with 2 during-frames and an explicit "the placement refers to the object just carried and
released" note; scope hints appended to every predicate line. Candies rerun: all three put-downs now
read `InBasket=True` after the step by the checker itself (conf 0.71–0.77), verdict clean, nothing
adjudicated; the pick-up at 11.9 s correctly came back `not_visible` instead of False. Cost: effects
stage $0.096 (10 calls) vs ≈$0.05 before — the 2 during-frames add ~50% to each transfer check; the
binary head version (`transfer_released` item, now logged) removes that cost later.

## 4b. Calibration procedure (to run after the first human-labelled audit)

Inputs: every model self-report with its outcome. Sources already logged: item log (`teacher_confidence`
per item, later joined with gold/human/synthetic labels), verdict findings (`confidence`, adjudication
`confidence`) joined with human labels via `audit metrics`.

1. Per stage (scorer, boundary judge, predicate checker, adjudicator) collect pairs
   (confidence, correct) on the audit gold; keep episode ids as the group key.
2. Fit an isotonic-regression map (or 10-bin reliability table when n < 300) with 5-fold
   group-disjoint cross-validation; report ECE before/after with 95% group-bootstrap CIs — the same
   protocol laya's `calibration.py` uses for its temperatures.
3. Store `calibration/<stage>.json` = {bins or knots, n, ece_before, ece_after, ci95, fitted_on,
   prompt_version, model}. A calibration map is only valid for the prompt version and model it was
   fitted on; a prompt edit invalidates it (the item log records both).
4. Apply at runtime: `conf_cal = map(conf_raw)` in the reconciler and router; thresholds
   (`human_conf_below`, `adjudicate_confirmed_below_conf`) then operate on calibrated values, and
   `adjudicate_all_confirmed` can be switched off once ECE for that stage is below ~0.05.
5. For trained heads, calibration is temperature scaling on held-out logits (laya), fitted per
   question type, stored in the head's config; the same reliability report is produced.
6. Re-check monthly and whenever the teacher model, prompt version, or task family changes; a
   drift in ECE above 0.1 re-enables `adjudicate_all_confirmed`.

## 4. Confidence: current state and plan

Today every confidence is a model self-report (see prompts in `procqc/rubric.py` for the rubric each
stage is asked to follow); the reconciler's constants (0.7/0.85/0.95) are priors. Plan:

1. rubric in every prompt (done 2026-09-23);
2. audit → calibration bins and ECE per stage → isotonic maps stored with the graph;
3. self-consistency (3 samples over frame subsets) for confirmed high-impact findings;
4. token log-probabilities for yes/no items if Fuelix exposes `logprobs` (check);
5. calibrated heads (§3) make confidence a probability by construction.

## 5. Known model failure modes to design around

* Direction ambiguity on mirror actions (open/close, attach/detach) from 3 frames → mirror-pair
  hint added; binary first-frame/last-frame state items solve it structurally.
* "Not visible" answered as False → structural visibility fields + regex net added (2026-09-23);
  a `not_visible` answer class in the heads makes it a first-class outcome.
* Truncated JSON when reasoning tokens exhaust `max_tokens` → retry-on-truncation added; heads
  have no generation, so this disappears.
* Expected-next priming: the localized candidate list biases the scorer toward the expected step;
  keep the "other steps" section and the soft decoder prior; binary per-step items remove the
  competition framing entirely.
* Repeated-object ambiguity in effect checks ("candies in basket" while the next bunch lies on the
  table) → instance-specific predicates or end-of-episode-only goals; heads inherit the problem.

## 6. Localizer benchmark (24 Sep 2026) — what it says about the levers

Full report: `docs/benchmarks/2026-09-24_localizer_benchmark.md`; harness `procqc/localize/bench_lightwheel.py`.

* GDM (17 QC videos, step list given): loc-only F1@IoU0.5 48.9 with the motion proposer vs 45.7 / 41.1
  for the earlier GDM pipelines. Lightwheel held-out 25: 39.9, level with the old monolithic run and
  below the decomposed pipeline (44.4), because we predict 0.62 segments per GT segment.
* Boundary refinement is the largest single gain in every arm (Lightwheel oracle F1@0.5 26.2 → 36.9;
  GDM motion 28.3 → 43.2). A second round is the cheapest untested lever.
* Hand tracking lifts the proposal ceiling (GT segments with both endpoints in the snap menu at 0.5 s)
  from 19 % to 70 %, but the localizer realizes only part of it: after refinement F1@0.5 is 40.7 vs
  43.2 (motion), while recall, boundary tolerance and F1@10/25/50 favour tracking. The bottleneck
  moved to labeling the shorter windows (wrong-label overlaps 37 vs 23) — exactly the decision the
  distilled window head (§3) is meant to take over, and the place to spend more frames per window.
* Window floor 0.9 s excludes 29 % of Lightwheel GT segments outright; lowering it trades scoring
  cost for recall and should be evaluated with the item log on.
* Cost per video: $0.29 (GDM motion) to $0.42 (Lightwheel caption incl. drafting); scoring and
  refinement roughly equal.

## 7. Direct arm v2 (narrate → judge), 25 Sep 2026

`procqc/direct/narrate_judge.py`, `--mode narrate`. One native-video narration call (persona:
procedural-QC observer; rules from the GDM dense-description prompt plus explicit state changes,
matched step ids, scene start/end) followed by seven text judges (one per taxonomy kind) that get
the complete graph context and cite narration entries. Report:
`docs/benchmarks/2026-09-25_direct_arm_v2_narrate_judge.md`.

* CaptainCook4D (10 real recordings): omission 6/8 at 0.75 precision, 0/4 clean flagged, first
  parameter-deviation detections; $0.27 per 13-minute recording vs $0.37 for five video calls.
* Cost structure: narration ≈ 70–90 % of the bill; judges ≈ $0.04 for all seven; re-judging after a
  prompt change is cents because narrations are cached. Iterate on judges freely; treat the
  narration prompt as expensive to change.
* Levers: (a) narration at lower fps / media resolution for long recordings (the 900-frame cap
  already applies); (b) distil the narration into Laya heads per entry field (action, object,
  state change, matched step) — the narration IS the item log for this arm; (c) the judges are
  text-only and could move to a cheaper model once calibrated; (d) step-instance disambiguation
  for repeated identical steps is the open accuracy problem, not prompt length.

## 8. Latency instrumentation (25 Sep 2026) — profile cost AND latency from the same meter

Every accounting row (`procqc/pricing.py`, per stage and per model) now carries, next to tokens
and USD: `wall_s` (elapsed time of the stage as measured around it), `call_time_s` (sum of the
individual provider-call durations, request sent → response received; exceeds `wall_s` when calls
run concurrently), `retry_wait_s` (time slept between retries on 503s/timeouts, kept OUT of
call time) and `n_retries`. Both clients record them on every call (Fuelix via `LLMClient`,
Google via `GenAIVideoClient`, incl. Files-API upload as stage `video_upload`). Every verdict has
`timing_s.end_to_end_s` plus a per-stage breakdown; every run summary (`procqc.audit.cli run`,
`procqc.direct.arm run`) has a `latency` block with p50/p95/mean/max per stage and end to end, and
`realtime_factor` (video seconds processed per wall second). `procqc.audit.cli latency <verdicts>`
prints the same report for any existing run without model calls.

Rule (Ujjawal, 2026-09-25): latency is profiled from the runs we do anyway; never rerun models
just to measure latency. Historic runs before this change lack `call_time_s`/`retry_wait_s` and
show 0 wall for Fuelix sub-stages that were not wrapped; they are reported as `-`/0, not re-run.

Measured so far (before the concurrent-judges change): narrate arm end-to-end p50 307 s per
CaptainCook4D recording (median 10.9 min video → 1.3× realtime), narration call p50 56 s,
adjudication p50 33 s, seven sequential judges ≈ 160 s (now concurrent). Old per-kind arm p50 178 s.
Retry waiting inflated three narrations to 650–975 s; it is now a separate column.

## 9. Start / end signal verifier (12 Oct 2026) — a small-choice item that a local model could take

`procqc/signals/gesture_verify.py`. The Snowbird rubric's start and end signal is two thumbs up
(recording_start / recording_end). The sensor event log (Physical AI/procqc `signals/sensors.py`,
unchanged) decides most markers for free; only markers it reports as one-handed or missing go to one
Fuelix gemini-3.8-flash call (6 frames at 768 px, reasoning "low") that says what the frames show.

* Meta_Pilot, 100 recordings: the sensor log flagged 21 markers (start: 3 missing + 12 one-handed;
  end: 6 one-handed). Reviewers scored recording_start and recording_end perfect on all 100.
* Verifier v1 cleared 19 of 21 and confirmed 2 as missing (34dd1950, 75670975), both scored perfect →
  2 false confirmed flags. In both, the hands were held out in a deliberate signal with the thumbs
  angled rather than upright.
* Verifier v2 (`--verifier v2`, v1 still the default) adds the answer "other_signal" (a deliberate
  hand signal that is not a clear thumbs-up) → needs_review; "none" (no deliberate signal) is the only
  answer that confirms a missing signal. Re-check of the 2 (`out/internal/meta_pilot/gesture_verify_v2_recheck`):
  34dd1950 other_signal → review; 75670975 two_thumbs_up → pass. The second changed on the **same
  frames** (v1 said "none"), so it is model variance, not the new option. v2 has not been run on the
  other 19 markers.
* Measured cost: $0.0062 per call (the meter now works in worker threads). The v1 run on 21 markers was
  therefore about $0.13, not the ~$0.06 estimated.
* Not measurable on this set: recall on a really missing signal (no human negatives in the 100).

Levers:

| Lever | Expected effect | Cost | Status |
|---|---|---|---|
| Self-consistency: 2 calls on different frame subsets, keep the stricter answer | removes the same-frames flip seen on 75670975 | ≈ $0.25 for 21 markers | not tried |
| More frames over the marker (6 → 10–12) | fewer misses on short or tilted gestures | +60–100 % image tokens | not tried |
| Small local open VLM per frame: "two thumbs up / one / other signal / none / unclear" | no per-call cost, local latency | needs a separate env (torch, newer transformers; system Python 3.9 has transformers 4.57, no torchvision) and a weights download | candidate: smallest Qwen3 vision model (user, 12 Oct: no licence issue). Laya-vision weights rejected: CC BY-NC-SA, non-commercial |
| Calibrated head (§3) trained on this item | probability by construction, 100–1000× cheaper | needs labelled markers, incl. negatives | the verifier logs (`gestures.jsonl`) + reviewer scores are the first labels |

Notes for a local model: a model that takes several images can get the same 6-frame question and the
same answer set, so the comparison is like for like. A single-image model is asked once per frame and
the answers are combined in code ("any frame with two thumbs up" → pass), which is a different check;
either way, compare on the same 21 markers before switching. The hard cases are only
the borderline ones (thumbs angled, fingers loosely closed, fisheye view), because the sensor log
already passes the clear ones, so a small model must be judged on those, not on clear thumbs-ups.
