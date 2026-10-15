# Direct arm v2: narrate, then judge against the full graph (25 Sep 2026)

Redesign of the direct arm after the per-kind-video arm's smoke and CaptainCook4D results. Design
per Ujjawal's direction: reuse the dense-description stage of the earlier Lightwheel decomposed
pipeline, re-purposed for procedural QC, then compare the narration with the complete procedure
graph. Code: `procqc/direct/narrate_judge.py`, run with `procqc.direct.arm run ... --mode narrate`.

## Design

| stage | model / calls | input | output |
|---|---|---|---|
| 1. Narrate | 1 native-video call (Google AI Studio, ≤ 900 frames) | procedure graph as vocabulary context; persona: procedural-QC observer; rules adapted from `description_updated_prompt.txt` (one entry per distinct manipulation, consolidate only exact repeats, never invent, hands, source/destination, object identity, quantities/settings, timestamps) plus QC additions (explicit before → after state change per entry, `matched_step_id` only when action + object + outcome match, scene at start, state of task objects at end) | timestamped JSON timeline, scene_start, scene_end, notes |
| 2. Judge | 7 text calls (Fuelix), one per taxonomy kind | the COMPLETE graph context (topological steps with prerequisites, permitted repeats, terminal step, expected durations, preconditions/effects, objects with aliases, initial and goal state, expected results, start/end rules, pitfalls), the narration, the symbolic replay of the narrated step sequence as a hint, and a long definition + decision procedure + boundary rules for that kind | findings citing narration entries, with a context span for the reviewer |
| 3. Adjudicate | as other arms (frames from the finding and context spans) | | verdict JSON |

Kind definitions are mutually exclusive by construction (no cross-kind reconciliation rules):
early termination = mandatory final step never performed / goal not reached, regardless of how the
file ends; omission = required step never performed although a dependent step or the final step
was; misordering = step before a step it requires that is performed later; repeat, off-graph
addition (must serve no step at all), wrong tool/object/ingredient, parameter deviation.

## CaptainCook4D, 10 recordings, real labels, strict (confirmed findings)

| kind | gold | old arm (5 video calls per episode) | narrate → judge, first prompt | **narrate → judge, final** |
|---|---|---|---|---|
| omission | 8 | 5 TP / 1 FP / 3 FN | 6 / 2 / 2 | **6 / 2 / 2** |
| misordering | 1 | 0 / 1 / 1 | 0 / 1 / 1 | 0 / 1 / 1 |
| parameter deviation | 19 | not attempted | 1 / 2 / 18 | 1 / 3 / 18 (lenient 4 / 4 / 15) |
| wrong tool / object | 6 | not attempted | 0 / 0 / 6 (3 reported as parameter deviation) | 0 / 0 / 6 (2–3 as parameter deviation) |
| off-graph addition | 0 | 0 / 1 | 0 / **10** | **0 / 0** |
| repeat, early termination | 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| omission precision / recall | 0.83 / 0.63 | 0.75 / 0.75 | **0.75 / 0.75** |
| clean recordings flagged | 0 of 4 | 2 of 4 | **0 of 4** |
| episode verdict accuracy | 0.9 | 0.8 | **1.0** |
| routed to human | 30 % | 40 % | 30 % |
| cost per recording (12.8 min avg) | $0.37 | $0.27 | $0.27 (re-judge from cached narration: $0.01) |

The ten false off-graph findings of the first prompt were preparation actions the judge had been
told to report as "minor additions in service of a step" (fetching the tuna can, washing lettuce,
halving the avocado). The definition now treats anything that serves a step as ordinary work; only
actions serving no step are additions. Re-judging cost $0.10 because narrations are cached.

## What the narration does for the judge

28_26 (three labelled omissions): 65 entries, 12 matched to steps, state changes such as
"avocado: whole → cut in half, pit removed" and "lettuce leaf: flat → folded/rolled (empty)".
The omission judge cited them and found all three; the termination judge, asked only whether the
mandatory final step was performed, returned nothing. The old arm had reported a spurious
termination here and needed a reconciliation rule; v2 needs none.

Parameter deviations detected for the first time: two eggs cracked where the recipe says one, two
tablespoons of salsa instead of one, an English muffin torn by hand instead of cut (labelled as a
wrong-tool error, reported under both kinds: a boundary case between those two kinds, not a miss).

## Remaining failure: counting repeated near-identical steps

The two skipped-first-microwave recordings (1_10, 1_28) fail in every arm. The recipe has three
microwave cycles; the narrator matches the first cycle it sees to the first microwave step, and
everything downstream shifts ("stir omitted", "stir before microwave"). Fixing this needs either
step-instance disambiguation in the narration (which cycle, by count and by what happened
before) or a symbolic alignment of the narrated sequence to the graph that allows a skipped
prefix, rather than a longer prompt.

## Cost profile

Narration ≈ 65–90 % of the cost (one video call: 115 k prompt tokens at ≤ 900 frames); the seven
judges together ≈ $0.04; adjudication ≈ $0.03. Everything after the narration is cheap to iterate:
prompt changes to a judge re-run for cents. The narration is also the training corpus for the
Laya-style heads: every entry is a small typed statement (action, object, state change, matched
step) with a timestamp.

## Does detection depend on the narration's timestamps? (27 Sep 2026)

Measured against the CaptainCook4D step annotations on the 10 recordings:

| | value |
|---|---|
| performed GT steps with a matched narration entry | 126 / 132 (95 %) |
| order of matched steps vs GT order | 771 / 773 pairs agree (99.7 %) |
| raw start-time error, median / p90 | 84 s / 481 s |
| after normalization, median / p75 / p90 | 15.5 s / 36 s / 62 s (GT step median length 36.5 s) |

The raw timestamps were wrong in 6 of 10 narrations for two formatting reasons, not perception:
two narrations wrote minutes and seconds as one number (4:35 → 435); four ran a uniformly fast
clock (last action at 1.2–1.66× the video length, straight-line fit slope 0.60–0.83). Both are
detected deterministically (timeline ends after the video) and normalized in
`normalize_narration_times` (MM:SS reinterpretation when the seconds part is < 60 for every value
≥ 100; otherwise rescale to the video length); the narration prompt now spells out the seconds
format. Applied offline from the cached raw responses; findings re-timed from the narration entries
they cite.

What depends on what:
* **Omission, misordering, repeat, termination, wrong tool, parameter deviation: no dependence on
  absolute timestamps.** The judges read the narration as an ordered, indexed list and decide by
  presence, order, count and state changes; scoring matches by kind and step id. All findings of
  the run were made while 6 narrations had timestamps off by minutes; none changed after the fix.
* **They do depend on segmentation in two other senses:** enumeration (a merged or split entry
  changes counts and matched ids) and step matching (the microwave-cycle miscount). Those are the
  real accuracy drivers.
* **Timestamps matter for:** the adjudicator's frames (sampled at the finding and context spans;
  with the raw clocks, 6 recordings' adjudication frames were from the wrong moment), off-graph
  additions (scored by time overlap because they have no step id), the demo's frames, tag-and-retain
  segment outputs, and every temporal metric (boundary F1, MoF). After normalization the median
  error is well under one step length, adequate for frame selection; still coarse for boundaries.

## Adjudicator frames from annotator timestamps (27 Sep 2026)

In the annotation-tool integration, annotator timestamps are more accurate than a model's clock.
They are now used for exactly one thing: choosing the adjudicator's frames (`--annotations`;
`_annotated_windows` / `_annotated_frames` in `procqc/direct/arm.py`). The narrator and the judges
never see the annotations, because the annotations are themselves under test. When the detector's
window does not overlap the annotated one, both are shown to the adjudicator, labelled.

Re-run of the adjudication stage only (`procqc/direct/readjudicate.py`), same findings, same
narrations; CaptainCook4D 10 recordings, strict (TP / FP / FN):

| kind | frames from detector clock | frames from annotator timestamps |
|---|---|---|
| omission (8 gold) | 6 / 2 / 2 | 6 / 2 / 2 |
| parameter deviation (19 gold) | 1 / 3 / 18 | **3** / 3 / 16 |
| misordering (1 gold) | 0 / 1 / 1 | 0 / 1 / 1 |
| wrong tool / object (6 gold) | 0 / 0 / 6 | 0 / 0 / 6 |
| micro precision / recall | 0.54 / 0.21 | **0.60 / 0.26** |
| clean recordings flagged | 0 of 4 | 0 of 4 |
| routed to human | 30 % | **20 %** |

Adjudication cost $0.36 for the 10 recordings (19 narrate, 19 classify, 16 advocate calls);
latency p50 22 s, p95 58 s per recording.

Incident during this work: the latency instrumentation added a module-level reference to the
pricing module in the Fuelix client without importing it; every Fuelix call raised NameError and
the adjudicator's exception handlers turned each failure into "escalate". The first re-adjudication
run was therefore invalid (kept as `out/.../_invalid_narrate_annframes_nameerror`). Fixed, and
three tests now drive the client's sync, async and retry paths with a fake provider; adjudication
stage failures are recorded as `errors` on each adjudication and counted as `adjudication_errors`
in verdicts and run summaries, with a warning, instead of passing silently as decisions.
No earlier run was affected (all stored verdicts scanned).

## Synthetic smoke set with the current pipeline (28 Sep 2026)

Same 15 episodes as the earlier smoke tests, narrate → judge, adjudicator frames from the
re-timed ground-truth segments. $1.51 total ($0.10 per ~1-minute episode); end to end p50 52 s,
p95 109 s (narration 27 s, seven judges in parallel 12 s, adjudication 21 s). Strict TP / FP / FN
(previous per-kind video version in brackets):

| kind | current | previous version |
|---|---|---|
| early termination | 2 / 1 / 1 | 3 / 2 / 0 |
| off-procedure addition | 2 / 0 / 1 | 2 / 2 / 0 (+1 TP, +1 FP at review) |
| omission | 0 / 3 / 3 | 1 / 2 / 2 |
| repeat | 0 / 0 / 3 | 0 / 0 / 1 (+2 TP at review) |
| misordering | 1 / 1 / 2 | 1 / 1 / 2 |

Fewer false alarms, but the narration flattens two kinds: it merges a duplicated step into one
entry (rule 2 consolidates exact repeats; meant for strokes and passes, it also swallows a whole
repeated step), and it labels steps in the written order when the step list is in its prompt, so
a swapped pair can come out in canonical order (1337afbe_swap05 was caught by the previous
version, missed now). One termination was missed because the narration reported the final step
as done; one inserted 'sit down' clip was matched to a listed step. Decision page:
`docs/architecture/taxonomy_readiness.html`.

## Fix round 1 (28 Sep 2026): results mixed, second round prepared

Changes tested (runs `out/opensource/captaincook4d/narrate_v3`, `out/synth_lightwheel/narrate_smoke_v3`):
weak trailing steps (reposition, stand up) made optional and the last state-changing step made the
mandatory final step (`procqc/graph/verbs.py`, `chain_graph_from_gt`); narrator given an
alphabetical action vocabulary without step ids or order, a repeat rule (a finished action done again
is a new entry) and a `scene_change` flag; a separate text MATCH stage assigning steps by content with
look-alike candidates, plus a deterministic position convention for look-alike steps
(`IDENTITY_CONVENTION`, `resolve_lookalikes`); judge procedures rewritten as numbered checklists
(termination decided by the goal / final step result, wrong tool takes precedence over parameter,
parameter `subtype`); adjudicator told that segments are detector claims, shown two end-of-video
frames for omissions and the mandatory final step / goal, and asked to reclassify an omission as
early termination when the goal is not visible at the end; two shared boundary rules aligned with the
mutually exclusive definitions.

Strict TP / FP / FN, before → after:

| | before | after round 1 |
|---|---|---|
| CC4D omission (8 gold) | 6 / 2 / 2 | 4 / 0 / 4 |
| CC4D parameter deviation | 3 / 3 / 16 | 2 / 3 / 17 |
| CC4D repeat, termination, misordering FP | 0, 0, 1 | 3, 1, 2 |
| CC4D clean recordings flagged | 0 of 4 | 1 of 4 |
| synthetic off-graph addition | 2 / 0 / 1 | **3 / 0 / 0** |
| synthetic misordering | 1 / 1 / 2 | 2 / 3 / 1 |
| synthetic termination | 2 / 1 / 1 | 1 / 0 / 2 |
| synthetic omission | 0 / 3 / 3 | 0 / 5 / 3 (20 FP incl. human review) |
| synthetic routed to human | 13 % | 80 % |
| cost (CC4D 10 + synthetic 15) | $2.8 (CC adjudication only) + $1.51 | $3.22 + $3.62 |
| synthetic end-to-end p50 | 52 s | 192 s (match stage p50 102 s) |

What worked: the look-alike convention fixed 1_28 (true omission of the first microwave found, the
old stir / continue-microwave false alarms gone); `scene_change` fixed eb7d161e_ins01 (inserted
footage now an off-graph addition instead of a false termination) and kept the other insertions.

What went wrong, and the round-2 change for each (implemented, tested offline, not yet re-run):
* One narration entry ("pick up the book and place it on the cover") could claim only one of the
  two fine-grained Lightwheel steps, so the other looked omitted at 0.95; the adjudicator rejected
  them and the disagreement policy escalated each one (80 % review). → the matcher returns
  `step_ids` (several consecutive steps per entry), the entry's span is split between them; weak
  steps (reposition, adjust, sit down) are optional anywhere in the synthetic graphs (88 of 598
  steps; no label targets one).
* The position rule swapped pepper and salt in 28_10 / 28_25 (the matcher listed both as candidates
  although the entry named the ingredient). → the rule never overrides an entry that names
  something only its own step has (`_content_names`), and the matcher prompt restricts candidates.
* 1_10: one microwave cycle narrated as two button presses; the second was assigned to the first
  microwave step, turning the real omission into a misordering. → a look-alike entry directly
  continuing the previous one (no other step in between) is the same performance
  (`continues_entry`, segment extended). Offline replay: 1_10 now shows the first microwave never
  performed, 28_10 no longer swaps the seasonings.
* 28_10 (clean): mixing again after each seasoning was reported as a redundant repeat. → repeat
  definition: redoing a step because the object changed in between (an ingredient added) is not
  redundant.
* Match stage latency (up to 42 k hidden reasoning tokens, 654 s). → `reasoning_effort="low"` for
  that call (Fuelix passes it through; probe: reasoning 115 → 0 tokens).
* End-of-video frames: labelled "only to judge whether the task was completed", after 28_25 was
  reclassified as off-camera on end-state evidence.

Not fixable in the pipeline, verified on frames: b259cece_term1 — the book really is turned over at
55–57 s inside the annotated "cover the back page" step and ends back-cover-up; the synthetic graph
says only "Flip the book on the table", with no end state, so no matcher can tell that flip from
the missing final one. 30023601_term1 — the judge found the termination; the adjudicator mistook
the desk top for the shelf (frame at 37.5 s) and reclassified it as off-camera. 28_26 — the new
narration missed the empty-leaf rolling and the toothpick at the end (annotated at 750–790 s), so
termination was reported and the three annotated omissions were not.
