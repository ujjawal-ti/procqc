# Procedural Error QC for Physical AI Demonstrations
## Independent Validation of the Taxonomy & Guidelines, plus an Agentic Pipeline Recommendation

Prepared 2026-09-17 against:
- `Physical AI Data Quality Control.docx` (six-axis failure taxonomy, Auto-QC architecture)
- `Physical_AI__Procedural_ErrorsMistakes.pdf` (53-page per-error-type operational guideline)

Method: every benchmark, method and robot-learning claim in the two documents was checked against the primary source (arXiv/CVF/OpenReview/project pages) by four parallel research passes. Claims are marked **Confirmed**, **Partly**, **Not found** (no source supports it) or **Contradicted**. Where the documents are right, this report says so briefly; the detail is spent on what needs changing and on the pipeline.

---

## 1. Executive summary

**The taxonomy is sound and well aligned with the field.** Your six procedural types (omission, addition, misordering, wrong tool/object, early termination, correction loop) cover the "procedural" half of every published taxonomy (EgoPER, CaptainCook4D, EgoErrorVQA, HoloAssist, IndustReal, Epic-Tent, EgoOops, the 2025 survey). The subtypes and boundary rules are more granular than anything published and are a genuine contribution.

**The proposed Stage-3 method stack is the right family** (task-graph alignment + effect verification + VLM adjudication). It matches the current state of the art. But several method descriptions are inaccurate in detail, and one key assumption, that frontier VLMs can adjudicate zero-shot "with high precision", is contradicted by the benchmarks.

**Five things must change before the documents are used as engineering specs:**

1. Remove or re-label unsourced statistics. The six-axis frequency table and the "over 60% cascade" claim have no published source.
2. Correct the method descriptions of GTG2Vid, AEM and Ego-ADR (details in §4).
3. Reverse the default disposition for corrections and recoveries: label and keep them, do not excise by default. This is what Physical Intelligence, AgiBot World and 2026 reweighting methods do.
4. Drop spline "trim-and-stitch" as a default remediation. No published precedent exists and the closest work (MinInter, 2026) argues interpolated connectors degrade policies. Use segment-level tagging and down-weighting instead.
5. Redesign the VLM layer as an agentic, graph-grounded, decoupled-reasoning pipeline with human-in-the-loop and a self-evolving task graph, rather than a single zero-shot judge. §6 gives the design.

The paper you cited (arXiv 2609.09153, "Procedural Graphs: Self-Evolving Execution Structures for LLM Agents", Lu et al., Google, Sept 2026) is not a video or robotics paper. It is about giving tool-using LLM agents an editable procedure graph. Three of its ideas transfer directly and are built into §6: the graph schema with condition/guidance/pitfalls edges, "localize then judge" (a 2-hop subgraph beats the full procedure, and the full graph actively hurt embodied tasks in their ablation), and validation-gated self-evolution with a rejection memory.

---

## 2. Claim-by-claim verdicts

### 2.1 Benchmarks and datasets

| Claim in docs | Verdict | What the source says |
|---|---|---|
| CaptainCook4D: 384 recordings, 94.5 h, 5.3K step annotations, 10K fine-grained interaction labels | Confirmed (wording) | "10K fine-grained **action** annotations", not "interaction labels". |
| CaptainCook4D: uncorrected omission causes secondary failures in "over 60% of downstream tasks" | **Not found** | Paper only says errors "are combinatorial and can have a compounding effect". No number. Remove. |
| CaptainCook4D taxonomy (implied: omission/order) | Partly | Actual 7 classes: Preparation, Measurement, Timing, Temperature, Missing Step, Technique, Order. Four of seven are parameter/manner errors your taxonomy does not name (see §3.2). |
| EgoPER taxonomy: omission, addition, modification, slip, correction; multi-prototype contrastive learning | Confirmed | EgoPED: prototypes per step trained on error-free video only. |
| Assembly101: 4,321 videos; mistake labels | Confirmed | Labels are only {correct, mistake, correction}: 15.9% mistakes, 6.7% corrections. No mistake sub-types. |
| Assembly101: "mirror-like symmetries attach/detach"; policies loop assemble/disassemble | **Not found** | Not in the paper. This is your inference; label it as such. |
| Assembly101 "transitive vs intransitive propagation rules" | Unverified | Could not be located in Assembly101. Cite carefully or attribute to your own framework. |
| EgoErrorVQA defines "Propagated Wrong Order" | **Contradicted** | Eight classes: Wrong Object, Wrong Action, Wrong Order, Omission, Unintended & Unnecessary Action, Correct Wrong Action, Equipment Failure, Others. Propagated ordering errors are folded **into** Wrong Order. Your subtype 3.2 is a refinement, not a citation. |
| PIE-V (2026): augments Ego-Exo4D with controlled deviations | Confirmed | Same paper as "How to Correctly Make Mistakes" (arXiv 2604.15134, CVPRW 2026). 17 tasks, 50 scenarios, 102 injected mistakes, 27 corrections. Its own taxonomy is edit-distance style: Deletion, Insertion, Substitution, Transposition, Wrong Execution, + Correction. |
| PIE-V shows "error probability scales with cognitive load and task phase depth" | Partly | The error *planner* is conditioned on phase and a load score. The paper does not report this as an empirical finding about humans. Rephrase. |
| IndustReal POS = Damerau-Levenshtein without substitutions | Confirmed | Substitutions weighted 2 so they never win; POS = 1 − min(DamLev/|y|, 1). 42% of IndustReal videos contain errors. |
| HoloAssist mistake labels | Confirmed | ~6% of fine-grained actions are mistakes; corrected-by-instructor / corrected-by-performer / not-corrected. |

### 2.2 Detection methods

| Claim | Verdict | Correction |
|---|---|---|
| GTG2Vid: DP alignment with constant penalties λ_drop_node, λ_drop_frame | **Partly** | Penalties are **dynamic**: frame-drop cost is entropy-based `d^x_j = −(Σ_i C_ij log C_ij / log(1/2S) + η)`, node-drop cost `d^z_i = −τ(1 − max_j C_ij)`. The graph is **given at test time**, not learned. Metrics are F1@.5, EAcc, w-F1@0 (not EDA/AUC). Omission IoU is actually 5.7 pts *lower* than EgoPED. |
| AMNAR: PAPB + RMB, min Euclidean distance to valid-successor prototypes, threshold τ_k | Confirmed | Threshold is the 0.85 quantile of normal-training distances per action. EgoPER EDA 64.4 / AUC 68.5. |
| AEM: ActionFormer end times, effect window [ed_k, ed_k+δ], canonical prototypes, τ_effect | **Partly / contradicted in detail** | No ActionFormer window. Effect frames are ranked by semantic relevance to a GPT-4o post-state description **plus Laplacian sharpness**. Detector is prompt-similarity ("An image showing [ACTION] for [TASK]"); mistake prob = 1 − cosine. Effect token is learned by contrastive alignment so GPT-4o/Grounding DINO are **not needed at inference**. EgoPER AUC 73.8 / EDA 66.7 (SOTA). |
| RegulAR: executable set E_t, impact score I_t formula, 5-second cadence, what/why/how feedback | Confirmed | φ(a) = 0.5·|desc(a)|/max + 0.5·dist/max. GPT-5 for graph generation, Gemini 2.5 Flash live. **No benchmark**: N=12 user study on two cooking tasks (omission F1 0.76 vs 0.32 baseline). |
| Ego-ADR: 3-stage decoupled VLM reasoning, "high precision" | **Partly** | Lives in the EgoErrorVQA paper, is zero-shot, and gains are modest: Qwen2.5-VL 12.8 → 19.6% MC accuracy; Video-LLaVA accuracy *fell* 44.2 → 13.6 (F1 rose). Best any model: 66.4% vs humans 85.9%. Do not describe as high precision. |
| arXiv 2602.09367 and 2606.00090 as sources for Ego-ADR / procedural detection | **Misattributed** | 2602.09367 = CAPER (LLM-constrained robotic lab experiments). 2606.00090 = "Silent Failures in Physical AI", a runtime-authorization literature review. Neither is a procedural mistake detector. |
| Frontier VLM zero-shot judge (Gemini 1.5 Pro / GPT-4o) | Stale and over-optimistic | Post-training paper (arXiv 2608.28406): zero-shot 7B VLM F1 on unseen recipes = 0; GRPO + "opposite reward" on paired clips → 48.0. Documented VLM failure modes: yes-bias, reasoning/answer inconsistency, duration heuristics instead of visual outcome, blindness to subtle cues. |
| MisFormer/MisEngine semantic-role attribution | Confirmed | Predicate/object roles via SRL; semantic F1 83.9 vs GPT-4o 77.2. |
| Survey 2510.19292 taxonomy | Confirmed | Procedural (omitted, unnecessary, corrective) vs Executional (technique, temporal, modification, scenario-specific). |

### 2.3 Robot-learning and data-curation claims

| Claim | Verdict | Correction |
|---|---|---|
| Belkhale et al. 2023: action divergence / transition diversity; quadratic compounding | Partly | Definitions confirmed. Their bound weights early-step divergence by (H − t); the **quadratic T²ε bound is Ross & Bagnell 2010**, not Belkhale. |
| robomimic: worse operators → worse policies | Confirmed | Square, BC-RNN: MH-Worse 36.7% vs PH-quality subsets far higher; offline RL "struggle[s] to deal with mixed quality human data". |
| DemInf, SCIZOR, CUPID | Confirmed | DemInf +5–10%; SCIZOR +15.4% avg (real robot +32.9 abs); CUPID matches SOTA with <33% of data. Add 2026: QoQ, ATHENA (influence functions at VLA scale), ReTVL (retry-supervised reweighting that **keeps** corrective behaviour). |
| Ambient Diffusion Policy routes suboptimal demos to high-noise bands only | **Partly** | Suboptimal data is used at high **and low** diffusion times; only mid-range is excluded. Up to 33% gain. |
| Six-axis frequency table (Recording 8–15%, Embodiment 20–35%, Execution 15–30%, Contact 10–20%, Procedure 5–12%, Protocol 25–40%) | **Not found** | No published source. Nearest data: DROID ~17% unsuccessful episodes; RH20T ~9% failures; AgiBot World ~1% failure-recovery episodes; Siemens 2026 QC study 28/100 failing. Replace with "to be measured" and the audit protocol in §7. |
| Trim-and-stitch with cubic Hermite splines in proprioception space | **No precedent** | Segment-level *selection/weighting* exists (SSDF 2025, HELP/VLAC 2026, ReTVL 2026). No paper splices with interpolation; MinInter (2026) argues interpolated connectors are non-expert transitions that hurt. |
| Hard-reject corrections from the "golden" set | Contradicted by practice | π0.7 keeps 1–5 quality scores and human-annotated mistake segments for conditioning; AgiBot World deliberately collects failure-recovery data; ReTVL down-weights the error but keeps the recovery. |

---

## 3. Taxonomy validation

### 3.1 Crosswalk to published taxonomies

| Your type | EgoPER | CaptainCook4D | EgoErrorVQA | Epic-Tent | EgoOops | PIE-V | CREAM phenotype (Hollnagel) |
|---|---|---|---|---|---|---|---|
| 1 Omission | omission | Missing Step | Omission | omit | — | Deletion | Sequence: omission |
| 2 Addition | addition | — | Unintended & Unnecessary | repeat, search | — | Insertion | Sequence: intrusion, repetition |
| 3 Misordering | — (under modification) | Order | Wrong Order (incl. propagated) | order | — | Transposition | Sequence: reversal, jump fwd/back |
| 4 Wrong tool/object | modification | Preparation | Wrong Object | misuse | Incorrect-object-use, Mispick | Substitution | Object: neighbour / similar / unrelated |
| 5 Early termination | — | (partly Timing) | — | failure | — | — | Duration: too short; Timing: premature stop |
| 6 Correction loop | correction | — | Correct Wrong Action | correction | Self-correction | Correction | — (recovery, not error) |
| *not in your list* | slip | Technique, Measurement, Timing, Temperature | Wrong Action, Equipment Failure | slow, motor | Accidental, Wrong-way | Wrong Execution | Force / speed / distance / direction; Duration too long |

**Reading the table:**

- Rows 1–4 are universal across every taxonomy. Your subtypes (1.1–1.4, 2.1–2.4, …) are finer than anything published and are worth keeping as your differentiator.
- **Early termination is under-represented in the egocentric literature** because those datasets record until the task is done. In robot teleop, where the operator controls the stop button, it is a first-class failure. Keep it, and cite robot-side evidence (DROID's idle filter, Siemens' "incomplete reset / premature release" findings, π0.7 mistake segments) rather than egocentric datasets.
- **Correction is classified as an error type by every egocentric dataset, but as a *valuable signal* by robot-learning practice.** Your guideline treats it as a defect to excise. Recommendation: keep the *detection* (it must be labeled) but change the *disposition* to "tag as recovery; retain; expose to training recipe" (§5).
- **A "parameter / manner deviation" class is missing.** Four of CaptainCook4D's seven classes (Measurement, Timing, Temperature, Technique), EgoErrorVQA's Wrong Action, PIE-V's Wrong Execution and CREAM's force/speed/duration modes describe the *right step done with the wrong parameter*. In industrial teleop this is: wrong torque, wrong quantity, wrong dwell time, wrong insertion depth. Your 5.4 (partial dispensing) and Axis 3 (execution) touch it, but the boundary is undefined. Add a seventh type, **Step Parameter Deviation** (over/under quantity, duration, force, position tolerance), or explicitly assign it to Axis 3 with a boundary rule.

### 3.2 Recommended two-layer structure: phenotype vs genotype

Your documents interleave *what is observed* (omission, wrong object) with *why it happened* (lapse, schema capture, HFACS preconditions). Human-factors practice separates these:

- **Phenotype layer (observable, what QC detects).** Hollnagel's CREAM error modes map almost one-to-one onto your types: wrong sequence (omission, reversal, repetition, intrusion), wrong object (neighbour, similar, unrelated), wrong timing (premature, delayed), wrong duration (too short = early termination), wrong force/speed/distance/direction (= parameter deviation). Adopting CREAM as the phenotype backbone gives you a citable, exhaustive observable taxonomy and makes the "parameter deviation" gap obvious.
- **Genotype layer (causal, what ops feedback uses).** Reason's GEMS (slip / lapse / mistake / violation) + HFACS preconditions + SPAR-H performance-shaping factors. This layer is inferred, not detected, and belongs in the collection-ops feedback loop, not in the per-episode QC verdict.

One correction to your genotype mapping: you classify misordering as a *rule- or knowledge-based mistake*. In Reason/Norman/Hollnagel, order reversals of a well-known sequence are canonical **skill-based slips**. Whether a given misordering is a slip (operator knew the order) or a mistake (operator did not) determines remediation (interface/checklist vs retraining), so the guideline should ask the question rather than presume. Post-completion error (your 1.3) should cite Byrne & Bovair 1997.

### 3.3 Boundary rules: validated

Your six boundary-rule families (permissible reordering, pre-satisfied off-camera state, conditional/optional steps, style variation vs addition, adaptive micro-adjustment vs correction, protocol-mandated redundancy vs compulsive re-check) correspond exactly to the open challenges listed by the 2025 survey ("permissible variation vs mistake", "error propagation", "compositional hierarchies"). They are also precisely the cases where RegulAR's executable-set check and AMNAR's multi-successor prototypes exist to prevent false positives. This is a strong section. Two additions:

- **Permissible functional equivalents** (your 4.A) need an explicit `allowed_substitutes` attribute in the task graph, otherwise the object grounder will flag every equivalent bolt grade.
- **Multi-pass operations** (your 6.B) and **protocol-mandated re-checks** (your 2.B) both reduce to "is the repeat a node in the graph?", which argues for encoding `permitted_repeats` per node rather than relying on the judge.

---

## 4. What the evidence says about the proposed Stage-3 stack

**Right family, wrong confidence level.** Graph-grounded detectors (AMNAR, GTG2Vid, DTGL/TGT, PREGO, RegulAR) are state of the art for omission and misordering; AEM is state of the art for outcome verification; MisFormer for predicate/object attribution. Composing them is correct. Three cautions the documents do not currently reflect:

1. **Absolute performance is low.** Best EgoPER error-detection F1@.5 is 33.0 (GTG2Vid); best EDA/AUC ~67/74 (AEM). Best VLM on EgoErrorVQA multiple choice is 66.4% vs 85.9% human. These are cooking/assembly egocentric videos with clean step vocabularies. Nothing has been measured on third-person + wrist-camera robot teleop with a gripper instead of hands. Plan on **domain adaptation and your own labeled set**, not on off-the-shelf checkpoints.
2. **Zero-shot VLM adjudication is the weakest link, not the safety net.** The documents route "ambiguous" cases to a frontier VLM. The post-training paper shows a 7B VLM scoring F1 0 zero-shot on unseen recipes, with systematic yes-bias and duration heuristics. The fix that works is (a) decoupled reasoning (narrate neutrally, then classify against the local subgraph and explicit boundary rules), (b) grounding (boxes, gripper state, effect frames) in the prompt, (c) post-training on paired correct/incorrect clips of the same step. §6 builds all three in.
3. **Task graphs are the real dependency.** Every strong method consumes a task graph; none learns it well from a handful of demos. RegulAR generates graphs from text with GPT-5; DTGL/TGT learns adjacency from step sequences (CaptainCook4D graph F1 87.8). The Procedural Graphs paper shows LLM refinement can grow a graph from a skeleton and even repair a flawed expert prior. Graph authoring, validation and evolution should be a named workstream with its own metrics.

**Stage 4 (DemInf / SCIZOR / Ambient) is complementary and should stay.** Add CUPID/QoQ/ATHENA (influence functions) as the 2025–26 alternatives and ReTVL for retaining recoveries.

---

## 5. Disposition policy: replace the three-way gate with rich labels

Current design: `Hard Reject | Trim-and-Stitch | Golden`. Recommended design, matching what π0.7, AgiBot World, HELP/VLAC and ReTVL actually do:

Per episode:
- `quality_score` 1–5 (human-calibratable, as in π0.7)
- `verdict`: `clean | flagged_minor | flagged_major | reject`
- `reject_reasons` from Axes 1–2 (sensor desync, PII, out-of-FoV) only

Per segment (from the Graph Verifier):
- `segment_tag`: `progress | idle | error | recovery | background`
- `error_type` from the taxonomy + subtype; `violated_precondition`; `evidence_frames`; `impact_score I_t`
- `reversible: bool`, `workspace_damaged: bool`

Training-recipe consumers then decide: filter, down-weight (ReTVL), mask error spans but keep recovery, ambient-partition, or condition on quality score. **Do not splice.** If a corrupted span must be removed for a specific policy class, cut at segment boundaries and train with episode masks; no synthetic connectors.

---

## 6. Agentic pipeline design

### 6.1 Why agentic, and what "agentic" should mean here

Not "a VLM that talks to itself". The value is in **decomposition, tool grounding, structured verification, and a learning loop over the reference procedure**. Three findings drive the design:

- Procedural Graphs ablation: localized 2-hop subgraph + LLM-rendered guidance beat both no-graph and full-graph injection; full-graph injection *hurt* the embodied benchmark (72.6 → 54.5). So: **segment first, judge each segment against its local neighbourhood.**
- Ego-ADR and the transparent-PMD line: **neutral narration before classification** reduces hallucinated errors.
- Procedural Graphs self-evolution: **contrast failed vs successful trajectories, propose graph edits, accept only if held-out performance does not drop, remember rejections.** For QC, "failed trajectories" = flags a human overturned; "successful" = flags a human confirmed.

### 6.2 Architecture

```
                    ┌──────────────────────────────────────────────┐
                    │ L0  Procedural Graph Store (per task)         │
                    │  nodes: keysteps w/ grounded pre/effects       │
                    │  edges: LEADS_TO | TRIGGERS | PROVIDES_INPUT  │
                    │         | CONVERGES_TO | CORRECTS (back-edge) │
                    │  attrs: condition, guidance, pitfalls,        │
                    │         optional, conditional_on,             │
                    │         allowed_substitutes, permitted_repeats│
                    │         mandatory_terminal, settle_time       │
                    └───────────────▲───────────────────┬──────────┘
                                    │ edits (gated)     │ 2-hop subgraph
  episode ──► [upstream: Recording-axis gate + shared signal primitives] ──► L2 Perception ──► L3 Agents ──► verdict JSON
              (owned by other axes, consumed here)                        tools               │               │
                                                        │               ▼
                                              L4 Human-in-loop router ─► audited labels
                                                        │                     │
                                              L5 Graph Refiner ◄──────────────┘
```

**L0 Procedural Graph builder.** Inputs: collection brief / SOP text, a few clean demos. LLM drafts nodes and edges (RegulAR pattern); DTGL/TGT-style transition statistics from clean demos validate ordering and discover parallel branches; a structural linter (acyclic except tagged `CORRECTS` back-edges, connected from Start, no dangling refs, non-empty attributes, vocabulary check) rejects malformed graphs. Every precondition and effect is a **grounded predicate** with a named checker (`IsOpen(cap) → effect-frame VLM check`, `IsGrasped(bolt_M6) → gripper width + Grounding DINO at PNR`, `IsLatched(cover) → F/T spike + VLM`).

**Upstream inputs (not part of the procedural pipeline).** This pipeline covers the Procedure axis only. Recording, Embodiment, Execution, Contact and Protocol are separate pipelines with their own checks. The procedural pipeline depends on them for exactly two things:

1. *A gate.* Run only on episodes the Recording axis has passed (valid clocks, all streams present). Procedural alignment on desynchronized data is meaningless.
2. *Shared signal primitives*, computed once by a common signal layer and consumed by every axis: gripper open/close events, idle spans, contact and release events from F/T, post-release kinetic decay, stop-record timestamp. Procedure uses them as step anchors and for rules 5.A (pause vs termination), 5.B (settling) and subtype 6.4 (oscillatory alignment); Execution uses the same events for slips and collisions.

Sharing primitives also resolves an overlap in the taxonomy: "unnecessary regrasping" (Execution axis) and subtype 2.1 "fiducial hunting / re-grasping" (Procedure axis) are the same observable event. One detector fires; each axis applies its own interpretation (grasp stability vs off-graph action). The same pattern applies to early termination vs Protocol "volume gaming" and wrong tool vs Contact affordance checks.

**L2 Perception tools (called by agents, not agents themselves).**
- Step segmenter: zero-shot video-text alignment (VideoCLIP / SigLIP-2 class) against node descriptions, later fine-tuned ActionFormer once labels exist.
- Proprio event extractor: grasp/release from gripper width, contact from F/T, dwell/idle spans, stop-record time.
- Object grounder + tracker: Grounding DINO + SAM2 on prompts from the local subgraph's `allowed_substitutes` and target objects; evaluated at the point-of-no-return (grasp closure) per your 4.B rule.
- Effect-frame selector: AEM's recipe, relevance to the node's effect description + Laplacian sharpness, over the post-segment window, plus the *first* frame for pre-satisfied checks.
- Scene-graph extractor: VLM → typed predicates over grounded boxes.

**L3 Agents.**

| Agent | Role | Inputs | Output |
|---|---|---|---|
| Orchestrator | Walks the segment list; retrieves 2-hop subgraph per segment; routes; enforces budget | segments, graph | ordered work items |
| Step Localizer | Assigns each segment to a node or `background/unknown`; confidence; fallback to full-graph match only when confidence < θ, and logs fallback rate | segment features, subgraph | aligned step sequence |
| Graph Verifier (symbolic, no LLM) | Executable-set check (RegulAR), DP alignment with dynamic drop penalties (GTG2Vid), POS score (IndustReal), terminal-goal check, back-edge detection | aligned sequence, graph | candidate flags: omission / misorder / addition / early_termination / correction, with topological impact I_t |
| Effect Verifier | For each node end, checks effect predicates on effect frames; at each node start, checks preconditions (catches pre-satisfied off-camera states); object identity at PNR | effect frames, boxes, predicates | predicate truth table with evidence frames |
| Adjudicator | Ego-ADR decoupled reasoning: (1) neutral narration of the segment, (2) match to expected node text, (3) classify against taxonomy + the boundary rules that apply to this node. Then a **devil's-advocate pass** that must argue the episode is clean; disagreement → lower confidence | narration, verifier flags, predicate table, subgraph `pitfalls` | structured verdict (schema below) |
| Human-in-loop Router | Sends low-confidence or high-I_t flags to human QC; samples accepted-clean episodes for audit | verdicts | audited labels |
| Graph Refiner (offline) | Contrasts overturned vs confirmed flags; proposes JSON edits (`add optional`, `add allowed_substitute`, `add conditional edge`, `revise pitfalls`, `add CORRECTS edge`); accepts only if held-out per-type F1 and clean-episode false-positive rate do not degrade; rejection memory prevents re-proposal | audited labels, graph | new graph version |

**Verdict schema (per segment flag):**

```json
{
  "episode_id": "...", "segment": [t_start, t_end], "node": "2.1_remove_cap",
  "error_type": "omission", "subtype": "1.1_prerequisite_unsealing",
  "violated_precondition": "IsOpen(vial)=False at start of 3.1_aspirate",
  "evidence": {"frames": [1832, 1840], "predicates": {"IsOpen(vial)": false},
               "grounding": [{"obj": "vial_cap", "box": [..], "conf": 0.91}]},
  "boundary_rules_checked": ["permissible_reordering", "pre_satisfied_offcamera", "conditional_step"],
  "impact_score": 0.82, "reversible": false, "workspace_damaged": true,
  "confidence": 0.71, "devils_advocate_agreed": false,
  "disposition_hint": "flag_major", "route_to_human": true
}
```

### 6.3 Design choices worth stating explicitly

- **Symbolic first, LLM second.** The Graph Verifier produces the flag; the Adjudicator explains, checks boundary rules, and can veto. This keeps recall high and puts the VLM where it is strongest (state description) rather than where it is weakest (unprompted error spotting).
- **Cascade by cost.** L1 ≈ ms; L2 segmenter/grounder ≈ seconds per minute of video; L3 Adjudicator only on flagged or low-margin segments. Procedural Graphs reports 15–70% token savings from localization alone.
- **Model choice.** Start zero-shot with a frontier VLM (Claude Fable 5.1 / Opus 5, Gemini 3.x, GPT-5 class) for the Adjudicator and a small open VLM (Qwen3-VL-8B) for narration. Phase 3 post-trains the small model with GRPO and the *opposite reward* on paired clips, where pairs come from (a) audited flags and (b) PIE-V-style synthetic error injection into clean demos.
- **Relax acyclicity deliberately.** The source paper forbids cycles; you need tagged `CORRECTS` back-edges so recoveries are recognized, not flagged as misordering.
- **Log fallback rate** of the Step Localizer as a graph-coverage metric; a rising rate means the graph is missing legitimate variants.

---

## 7. Evaluation plan and the audit that replaces the frequency table

1. **Golden audit set.** Stratified sample of ≥300 episodes per task family, dual-annotated with the taxonomy, boundary rules applied, adjudicated. Report Cohen's κ per error type; your HFACS intercoder-consensus source is the right template. This audit *produces* the frequency table the documents currently assert.
2. **Metrics.** Per-type precision/recall/F1 at segment level; temporal IoU; EDA and AUC (for comparability with AMNAR/AEM); **false-positive rate on clean episodes** (the cost of discarding good data is the number ops will care about); I_t calibration against human severity.
3. **Synthetic recall test.** Inject controlled omissions, transpositions, substitutions and truncations into clean episodes (PIE-V framework or edit-based clip reordering) to measure recall per type at known ground truth.
4. **Downstream test.** Train the same policy on (a) unfiltered, (b) filtered by verdict, (c) filtered + recovery-retained + down-weighted. Success rate is the only metric that ultimately justifies the pipeline.
5. **Graph-evolution test.** Held-out audited episodes; accept a graph edit only if per-type F1 and clean-FPR both hold (the paper's gating rule).

---

## 8. Prioritized recommendations

1. **Edit the documents** per §2: remove the 60% and frequency-table claims; correct GTG2Vid, AEM, Ego-ADR, Ambient, Belkhale attributions; fix the two misattributed arXiv IDs; re-word EgoErrorVQA and Assembly101 references.
2. **Add Step Parameter Deviation** as a seventh type (or a formal boundary to Axis 3) and adopt CREAM phenotypes as the observable backbone with GEMS/HFACS as the causal layer.
3. **Change the correction-loop disposition** to tag-and-retain, and drop spline stitching in favour of segment masks and reweighting.
4. **Make the task graph a first-class artifact** with schema, linter, versioning and evolution loop (§6.2 L0, L5).
5. **Build the agentic pipeline in phases**: Phase 0 audit (§7.1); Phase 1 graph + symbolic verifier + zero-shot adjudicator; Phase 2 grounding tools + effect verification; Phase 3 post-train the small VLM on audited/synthetic pairs; Phase 4 self-evolving graph with human-overturn feedback.
6. **Update the model and source list**: replace Gemini 1.5 Pro / GPT-4o with current models; add DTGL/TGT, PREGO/TI-PREGO, MisFormer, IndEgo, HELP/VLAC, ReTVL, QoQ, ATHENA, MinInter, Siemens 2026 QC study, π0.7 report, Procedural Graphs.

---

## 9. Cost-aware realization: tiers, models, and the frontier trade-off

Written 2026-09-21. Prices are list prices on that date (Anthropic first-party API; Google AI Studio paid tier; Modal on-demand GPUs). Gemini Flash prices are promotional through 2026-12-31 and double on 2027-01-01. Re-check before budgeting.

### 9.1 Design principles

1. **Decouple cost from video length.** Anything that touches every frame must be a frozen encoder or a deterministic rule, never a generative model. Generative models see only selected effect frames of flagged segments.
2. **Calibrated decisions, not generated text, in the bulk tier.** The laya-vision pattern (SmolVLM-256M fine-tuned with a proper scoring rule and temperature calibration to emit a typed `choice`/`score` in one forward pass, 71 ms per image on an L4, ECE 0.034) gives a calibrated probability per predicate check at negligible cost. Calibration is what makes routing to expensive tiers principled.
3. **Normal-only onboarding.** New clients supply clean demonstrations and an SOP, not labeled errors. EgoPED, AMNAR and DemInf all train on error-free data; thresholds are set at a quantile of normal-data distances (AMNAR: 0.85). Error labels arrive later from the audit loop.
4. **Frontier models where they are uniquely good:** authoring the task graph from SOP text, labeling a seed set for distillation, adjudicating the ambiguous tail, and periodic audits. Not bulk detection.
5. **Human review is the dominant cost.** At roughly 3 minutes per flagged episode and $15–25/hour, a human review costs $0.75–1.25, which is 30–100× the model cost of the whole cascade. False-positive rate matters more than any per-token price.

### 9.2 Tiered architecture with per-episode cost

Reference episode: 60 s, 3 cameras (2 wrist, 1 third-person), 30 fps, ~8 keysteps, proprioception. Costs are per episode; GPU seconds at Modal rates (L4 $0.80/h, L40S $1.95/h, H100 $3.95/h).

| Tier | What runs | Hardware | Latency | Cost / episode | Runs on |
|---|---|---|---|---|---|
| A. Deterministic | Recording gate, proprio events, idle spans, stop timestamp | CPU | <1 s | <$0.0001 | 100% |
| B. Frozen encoders + light heads | V-JEPA 2.1 clip embeddings (dense, temporally consistent) and/or SigLIP-2 frame embeddings at 4 fps; step localizer (text-aligned or prototype); AMNAR-style successor-prototype distance; GTG2Vid DP alignment; effect-frame selection (relevance + sharpness) | L4 | ~10 s wall, ms per clip | $0.002–0.004 | 100% |
| C. Calibrated decision head | laya-style SmolVLM-256M or Qwen3-VL-2B head answering typed predicate questions on effect frames ("IsOpen(cap)?", "Held object = M6 bolt?") with calibrated probability | L4 | 71 ms / image; ~1 s per episode | ~$0.0003 | 100% |
| C′. Small generative VLM (optional) | Qwen3-VL-4B/8B (Apache 2.0) for neutral narration and object identity on flagged segments | L40S / H100, vLLM | 0.3–0.6 s per call | $0.003–0.006 if all episodes; ~$0.001–0.002 amortized on flagged only | 20–40% |
| D. Frontier adjudicator | Decoupled reasoning + devil's-advocate pass on ~1.5 flagged segments per episode on average; 6 effect frames at 896×672 + 1.5k text in, 400 out | API | 5–20 s | see 9.3 | ~5–15% of segments |
| E. Human review | Low-confidence / high-impact flags, plus sampled audits | people | minutes | $0.75–1.25 per review | target ≤5–10% |

Tiers A–C run in milliseconds per clip on a single L4 and are fast enough to give operators live feedback on the rig (RegulAR-style), which is a free by-product of the offline design.

### 9.3 Frontier adjudicator cost per flagged segment

Claude bills images at ⌈w/28⌉×⌈h/28⌉ visual tokens (896×672 = 768 tokens) and has no native video input, so frames are sent as images. Gemini bills video at ~100 tokens per second at default resolution, sampled at 1 fps, so a 10-second clip is ~1,000 tokens. Both offer 50% off in batch mode. OpenAI GPT-5.6 text prices are listed (Terra $2/$12, Sol $5/$30); its image-token accounting was not verified here.

| Model | Input $/M | Output $/M | Per segment (online) | Per segment (batch) | Per episode at 1.5 segments (online) |
|---|---|---|---|---|---|
| Gemini 3.1 Flash-Lite | 0.25 | 1.50 | $0.0012 | $0.0006 | $0.002 |
| Gemini 3.8 Flash | 0.75 | 3.75 | $0.0034 | $0.0017 | $0.005 |
| Claude Haiku 4.5 | 1.00 | 5.00 | $0.008 | $0.004 | $0.012 |
| Gemini 3.1 Pro | 2.00 | 12.00 | $0.010 | $0.005 | $0.015 |
| Claude Sonnet 5 | 2.00 | 10.00 | $0.016 | $0.008 | $0.024 |
| Claude Opus 5 | 5.00 | 25.00 | $0.040 | $0.020 | $0.060 |

Prompt caching applies to the stable prefix (system prompt, taxonomy, boundary rules, graph schema); the per-segment subgraph and frames are the variable part. Cached reads are a fraction of input price on both providers, so the text portion is cheap. Image/video tokens dominate.

### 9.4 The trade-off: cascade vs frontier-only

Sending the whole reference episode (3 cameras × 60 s) to a frontier model with no cascade:

| Approach | Per episode | 10k episodes/day | Notes |
|---|---|---|---|
| Cascade A–C only (no LLM) | ~$0.003 | ~$30/day | Detection only; no explanations; recall depends on graph + prototypes |
| Cascade + Gemini 3.8 Flash adjudicator | ~$0.009 | ~$90/day | Good default when video-native tokenization matters |
| Cascade + Claude Sonnet 5 adjudicator | ~$0.027 | ~$270/day | Stronger reasoning on boundary rules; frames as images |
| Cascade + Claude Opus 5 adjudicator | ~$0.063 | ~$630/day | Reserve for the hardest 1–2% or for audit |
| Frontier-only, Gemini 3.8 Flash, 1 fps native video | ~$0.02 | ~$200/day | Cheap because of video tokenization, but zero-shot accuracy (see 9.5) and no grounding |
| Frontier-only, Gemini 3.1 Pro | ~$0.05 | ~$520/day | |
| Frontier-only, Claude Sonnet 5, 180 frames as images | ~$0.29 | ~$2,900/day | 10× the cascade; image tokens scale with frames |
| Frontier-only, Claude Opus 5 | ~$0.72 | ~$7,200/day | |

Two conclusions. First, if a frontier model must see raw video, Gemini's native video tokenization is roughly 7× cheaper than frame-by-frame images on any provider; that is a structural difference, not a price difference. Second, the cascade's value is not mainly the model bill. At 10k episodes/day, a 20% flag rate sends 2,000 episodes to humans at ~$2,000/day. Halving false positives saves more than the entire model cost of any row above. Spend engineering effort on precision (graph quality, calibration, effect verification), not on shaving token prices.

### 9.5 What the frontier actually buys in accuracy

Measured on published benchmarks, not extrapolated:

- **Zero-shot detection, small vs frontier.** EgoErrorVQA multiple choice: open 7B models 13–45%, GPT-4o 57.9%, best model 66.4%, humans 85.9%. The frontier adds 20–40 points over zero-shot small VLMs, and still leaves a 20-point gap to humans. Frontier zero-shot is not a finished detector.
- **Post-training closes most of the small-model gap.** GRPO with paired correct/incorrect clips and an "opposite reward" took Qwen2.5-VL-7B from F1 0 to 48 on unseen recipes (arXiv 2608.28406). Pairs are cheap to make from a client's own clean demos by clip deletion, reordering and repetition.
- **Graph-grounded small supervised models beat VLMs on the same data.** AMNAR EDA 64.4 / AEM AUC 73.8 on EgoPER, trained on normal videos only, versus VLM-based baselines that trail them. RegulAR, which pairs a GPT-5-authored graph with Gemini 2.5 Flash, reached omission F1 0.76 vs 0.32 without the graph.
- **Decoupled reasoning helps a little, grounding helps a lot.** Ego-ADR's narrate-then-classify added 7–8 points to a 7B model; adding boxes, gripper state and effect frames to the prompt is where RegulAR and AEM get their gains.

So the expected effect of upgrading the adjudicator from Gemini Flash / Haiku to Sonnet / Opus is better handling of boundary rules and better explanations on the ambiguous tail, worth a few points of precision on 5–15% of segments. It is not a substitute for the graph, the prototypes, or post-training. Measure it on the Phase 0 audit set before paying for it.

### 9.6 Client onboarding recipe (generic, config-driven)

Everything client-specific lives in three artifacts: a task-graph YAML, a predicate-checker registry, and a camera/rig config.

| Step | Input from client | What we do | Cost / time |
|---|---|---|---|
| 1. Graph authoring | SOP / work instructions, 3–5 annotated clean demos | Frontier LLM drafts nodes, edges, optional/conditional flags, allowed substitutes, mandatory terminals; linter validates; transition statistics from demos confirm ordering (DTGL/TGT) | ~20–50 LLM calls, <$5, one afternoon with a domain SME |
| 2. Vocabulary & grounding | Object/tool names, part numbers, bin layout | Grounder prompts and `allowed_substitutes`; test on 20 frames | hours |
| 3. Normal-only calibration | 20–50 clean demos | Frozen-encoder embeddings; per-step prototypes; 0.85-quantile thresholds; effect-frame descriptions per node | ~$0.10 GPU; minutes |
| 4. Synthetic error set | none (derived from step 3 demos) | Clip deletion → omission; swap → misordering; repeat → addition; truncate → early termination; object-swap via grounder mask where feasible | minutes; gives recall per type without labels |
| 5. Seed labels for the decision head | none | Frontier adjudicator labels 500–2,000 segments (batch, ~$5–40); SME spot-checks 10% | 1–2 days |
| 6. Decision-head fit | step 5 labels | laya-style calibrated head (proper scoring rule + temperature); 72k examples trained in 33 min on an A100 in the reference repo, so our 2k takes minutes | <$2 GPU |
| 7. Go live | — | Tiers A–D running; human router at conservative thresholds; audit sampling on | — |
| 8. Evolve | overturned vs confirmed flags | Graph refiner proposes edits, validation-gated, rejection memory; thresholds re-fit monthly | ongoing, small |

A new client with a new domain should reach a working pipeline in one to two weeks with no labeled errors, because every learned component in steps 3–6 is either normal-only or distilled.

### 9.7 Post-training roadmap (quality ladder)

| Stage | Model | Trained on | Expected effect | When |
|---|---|---|---|---|
| 0 | Zero-shot frozen encoders + frontier adjudicator | nothing | Baseline; high flag rate | week 1 |
| 1 | Calibrated decision head (256M–2B) | 500–2k frontier-labeled segments + synthetic errors | Bulk predicate checks at ~$0.0003/episode; calibrated routing cuts adjudicator calls 3–5× | week 2–3 |
| 2 | GRPO on Qwen3-VL-4B/8B with opposite reward | paired clips (synthetic + audited) | Small VLM approaches frontier zero-shot on in-domain detection (0 → 48 F1 in the reference paper) | month 2–3, once ≥300 audited episodes exist |
| 3 | Fine-tune V-JEPA 2.1 / ActionFormer for step segmentation | audited step boundaries | Better temporal IoU; fewer localization fallbacks | when fallback rate >10% |
| 4 | Graph self-evolution | overturned/confirmed flags | Fewer false positives from missing optional/conditional nodes | continuous |

Each stage is measured on the held-out audit set against the same metrics (per-type F1, clean-episode FPR, human-review rate). Promote a stage only if FPR does not rise.

### 9.8 Ensembling: where it pays

Ensembling across *signal types* pays; ensembling several similar VLMs does not. The cheap ensemble is already in the design: symbolic graph verifier (sequence), prototype distance (appearance), calibrated decision head (state predicates), proprio events (contact). Agreement → auto-accept or auto-flag; disagreement → adjudicator. A second frontier model as a tiebreaker on the 1–2% hardest cases is affordable (Opus 5 at ~$0.04 per segment) and is the one place a costlier model is clearly justified.

### 9.9 Reference-repo notes (laya-vision)

Reusable: the recipe (typed decision outputs, proper-scoring-rule training, temperature calibration, ~70 ms L4 inference, Modal deploy scripts), Apache 2.0 code. Not reusable as-is: the published weights are CC BY-NC-SA 4.0 because of ScienceQA training data, so train our own head from our labels. Start from SmolVLM-256M or Qwen3-VL-2B (Apache 2.0) as the backbone.

## 10. Sources consulted (primary)

Pricing and tokenization (2026-09-21): Anthropic model table (Fable 5.1 $10/$50, Opus 5 $5/$25, Sonnet 5 $2/$10, Haiku 4.5 $1/$5; batch −50%) · platform.claude.com/docs/en/build-with-claude/vision (28-px patches; up to 600 images/request; no native video) · ai.google.dev/gemini-api/docs/pricing (3.8/3.7/3.6 Flash $0.75/$3.75 through 2026-12-31; 3.1 Pro $2/$12; 3.1 Flash-Lite $0.25/$1.50) · ai.google.dev/gemini-api/docs/video-understanding (~100 tokens/s default, ~300 high, 1 fps) · morphllm.com/openai-api-pricing (GPT-5.6 Sol $5/$30, Terra $2/$12, Luna $0.20/$1.20) · modal.com/pricing (L4 $0.000222/s, L40S $0.000542/s, H100 $0.001097/s)

Small models and encoders: github.com/r33drichards/laya-vision · Qwen3-VL technical report arXiv 2511.21631 (2B/4B/8B dense, Apache 2.0) · V-JEPA 2.1 arXiv 2603.14482 · github.com/facebookresearch/vjepa2 · JEPA-VLA arXiv 2602.11832

### 10.1 Validation sources (benchmarks, methods, robot data quality, human factors)

Benchmarks: CaptainCook4D arXiv 2312.14556 · EgoPER (CVPR 2024) github.com/robert80203/EgoPER_official · Assembly101 arXiv 2203.14712 · HoloAssist arXiv 2309.17024 · EgoErrorVQA arXiv 2608.24134 · IndustReal arXiv 2310.17323 · PIE-V / How to Correctly Make Mistakes arXiv 2604.15134 · EgoOops arXiv 2410.05343 · Epic-Tent (ICCVW 2019) · IndEgo arXiv 2511.19684 · PREGO arXiv 2404.01933 · TI-PREGO arXiv 2411.02570 · Survey arXiv 2510.19292

Methods: GTG2Vid (ICCV 2025) github.com/robert80203/GTG2Vid · AMNAR arXiv 2503.22405 · AEM arXiv 2512.03474 (ICLR 2026) · RegulAR arXiv 2608.26715 (UIST 2026) · Post-training VLMs for mistake detection arXiv 2608.28406 · MisFormer/MATT arXiv 2511.20525 · Differentiable Task Graph Learning arXiv 2406.01486 · Video-Mined Task Graphs arXiv 2307.08763 · Procedural Graphs arXiv 2609.09153 · EGAgent arXiv 2601.18157 · TAMA arXiv 2510.00161 · CAPER arXiv 2602.09367 · Silent Failures review arXiv 2606.00090

Robot data quality: robomimic arXiv 2108.03298 · Belkhale et al. arXiv 2306.02437 · Ross & Bagnell 2010 · DemInf arXiv 2502.08623 · SCIZOR arXiv 2505.22626 · CUPID arXiv 2506.19121 · Re-Mix arXiv 2408.14037 · QoQ arXiv 2603.09056 · ATHENA arXiv 2606.16208 · ReTVL arXiv 2606.24633 · Ambient Diffusion Policy arXiv 2606.12365 · SSDF arXiv 2401.08957 · MinInter arXiv 2606.24078 · HELP arXiv 2607.09776 · DROID arXiv 2403.12945 · RH20T-P arXiv 2403.19622 · AgiBot World arXiv 2503.06669 · Siemens teleop QC arXiv 2605.26349 · π0.7 report pi.website/download/pi07.pdf · GR00T N1 arXiv 2503.14734 · AHA arXiv 2410.00371 · SAFE arXiv 2506.09937 · Code-as-Monitor arXiv 2412.04455 · RoboFAC arXiv 2505.12224 · RoboLineage arXiv 2606.22142

Human factors: Reason 1990 (GEMS) · Hollnagel 1998 (CREAM) · Byrne & Bovair 1997 (post-completion error) · HFACS · SPAR-H (INL)
