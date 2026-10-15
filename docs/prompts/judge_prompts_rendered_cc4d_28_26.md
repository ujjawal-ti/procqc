# Judge prompts as rendered for one real recording (CaptainCook4D 28_26)

Generated from `procqc/direct/narrate_judge.py` (`JUDGE_SYSTEM`, `KIND_DEFINITIONS`, `judge_prompt`).
Every judge call gets the same system prompt and the same first three blocks (procedure, narration, replay);
only the last block (the error kind) differs. The full omission prompt is shown, then the kind block of each other kind.

## System prompt (all seven judges)

```text
You are the second reviewer in a procedural quality-control process. You cannot see the video. You receive (a) the complete written procedure with its dependency structure, objects and expected states, (b) a timestamped narration of what happened in the video, written by an observer who was told to describe what they saw and not what was expected, (c) the result of an automatic replay of the narrated step sequence through the procedure graph, and (d) the definition of ONE kind of procedural error with its decision procedure and boundary rules.

Apply the decision procedure to the narration for that one kind only. Ground every finding in specific narration entries (cite their indices) and in the procedure's dependency structure. Do not report other kinds of error. Do not assume something happened off camera; if the narration is silent or uncertain about the decisive fact, say so in `episode_notes` and, if you still report, lower the confidence. Timestamps are seconds from the start of the video.

Confidence rubric (about your decision):
- 0.90-1.00: narration, predicate observations and the symbolic verifier all agree, and a boundary
  rule applies literally to the case;
- 0.70-0.89: the available evidence agrees but one source is missing or "unknown" (e.g. the object
  was not visible in the key frames);
- 0.50-0.69: the sources conflict, or the decision rests on inference rather than on what the frames
  show;
- below 0.50: the evidence is insufficient; choose 'escalate' rather than a low-confidence decision.
Return ONLY JSON matching the schema.
```

## User prompt, omission judge (complete)

```text
=== PROCEDURE ===
TASK: Spicy Tuna Avocado Wraps
CaptainCook4D recipe 'Spicy Tuna Avocado Wraps' with its published step dependency graph.

PROCEDURE STEPS in a valid order. Each step lists the steps it REQUIRES. Steps with no dependency path between them may be done in either order; that is not an error.
  step 1  [cc03_1_4_cup_mayonnaise_to_the]  1/4 cup mayonnaise to the bowl
      requires nothing; performed once
      expected result: 1/4 cup mayonnaise to the bowl
  step 2  [cc05_lay_out_2_large_lettuce_le]  Lay out 2 large lettuce leaves
      requires nothing; performed once
      expected result: Lay out 2 large lettuce leaves
  step 3  [cc11_take_1_ripe_avocado]  Take 1 ripe avocado
      requires nothing; performed once
      expected result: Take 1 ripe avocado
  step 4  [cc12_open_a_can_of_tuna]  Open a can of tuna
      requires nothing; performed once
      expected result: Open a can of tuna
  step 5  [cc04_drain_excess_water_from_ca]  drain excess water from can
      requires step 4; performed once
      expected result: drain excess water from can
  step 6  [cc10_add_1_can_drained_tuna_to]  Add 1 can drained tuna to the bowl
      requires step 5; performed once
      expected result: Add 1 can drained tuna to the bowl
  step 7  [cc15_1_tsp_sriracha_sauce_to_th]  1 tsp Sriracha sauce to the bowl
      requires nothing; performed once
      expected result: 1 tsp Sriracha sauce to the bowl
  step 8  [cc16_chop_1_scallion]  Chop 1 scallion
      requires nothing; performed once
      expected result: Chop 1 scallion
  step 9  [cc09_add_chopped_scallion_to_th]  add chopped scallion to the bowl
      requires step 8; performed once
      expected result: add chopped scallion to the bowl
  step 10  [cc07_mix_the_contents_of_the_bo]  Mix the contents of the bowl
      requires step 1, step 6, step 7, step 9; performed once
      expected result: Mix the contents of the bowl
  step 11  [cc02_season_1_4_tsp_pepper_on_t]  season 1/4 tsp pepper on the bowl
      requires step 10; performed once
      expected result: season 1/4 tsp pepper on the bowl
  step 12  [cc14_season_bowl_with_1_4_tsp_s]  Season bowl with 1/4 tsp salt
      requires step 10; performed once
      expected result: Season bowl with 1/4 tsp salt
  step 13  [cc17_cut_avocado_into_thin_slic]  cut avocado into thin slices
      requires step 3; performed once
      expected result: cut avocado into thin slices
  step 14  [cc01_place_avocado_slices_on_ea]  place avocado slices on each leaf
      requires step 2, step 13; performed once
      expected result: place avocado slices on each leaf
  step 15  [cc08_top_lettuce_leaves_with_th]  top lettuce leaves with the tuna mixture
      requires step 11, step 12, step 14; performed once
      expected result: top lettuce leaves with the tuna mixture
  step 16  [cc06_roll_up_the_lettuce_wraps]  Roll up the lettuce wraps
      requires step 15; performed once
      expected result: Roll up the lettuce wraps
  step 17  [cc13_secure_the_wrap_with_a_too]  secure the wrap with a toothpick
      requires step 16; performed once; MANDATORY FINAL STEP
      expected result: secure the wrap with a toothpick

=== NARRATION OF THE VIDEO (807.8 s) ===
SCENE AT START: The camera overlooks a kitchen counter beside a sink. Visible on the counter are an iPad showing instructions, a bottle of dish soap, a container of wipes, a bowl of butter, eggs, and an onion on a wooden board, along with a cutting board leaning against the wall.

TIMELINE (index. start-end s | hand | action | state change | matched step):
  #0. 2.8-5.0 s | left | open refrigerator door | refrigerator door: closed -> open | - (conf 0.95)
  #1. 44.5-47.8 s | both | pick up can of tuna from plastic bag in refrigerator to hand | can of tuna: in refrigerator -> in hand | 1 can | - (conf 0.95)
  #2. 48.8-50.2 s | right | close refrigerator door | refrigerator door: open -> closed | - (conf 0.95)
  #3. 51.5-53.0 s | right | place can of tuna from hand to counter | can of tuna: in hand -> on counter | - (conf 0.95)
  #4. 54.5-58.0 s | both | open drawer | drawer: closed -> open | - (conf 0.95)
  #5. 55.8-57.5 s | right | pick up can opener from drawer to hand | can opener: in drawer -> in hand | - (conf 0.95)
  #6. 60.5-80.5 s | both | cut can of tuna from counter to counter | can lid: sealed -> cut open around rim | cc12_open_a_can_of_tuna (conf 0.95)
  #7. 81.0-83.5 s | right | place can opener from hand to counter | can opener: in hand -> on counter | - (conf 0.95)
  #8. 91.5-113.5 s | both | squeeze can of tuna from hand to sink | tuna liquid: in can -> drained into sink | cc04_drain_excess_water_from_ca (conf 0.95)
  #9. 113.8-114.8 s | right | place can of tuna from hand to counter | can of tuna: in hand -> on counter | - (conf 0.95)
  #10. 119.8-122.5 s | right | pick up ceramic bowl from dish drying rack to counter | ceramic bowl: in rack -> on counter | 1 bowl | - (conf 0.95)
  #11. 123.5-127.0 s | right | pick up measuring cup from dish drying rack to hand | measuring cup: in rack -> in hand | 1/4 cup | - (conf 0.90)
  #12. 131.8-133.5 s | right | open cabinet door | cabinet door: closed -> open | - (conf 0.95)
  #13. 134.8-137.5 s | right | pick up mayonnaise squeeze bottle from cabinet shelf to hand | mayonnaise squeeze bottle: in cabinet -> in hand | - (conf 0.95)
  #14. 137.0-138.2 s | left | close cabinet door | cabinet door: open -> closed | - (conf 0.95)
  #15. 139.5-141.5 s | both | open mayonnaise squeeze bottle cap | mayonnaise bottle cap: closed -> open | - (conf 0.95)
  #16. 143.0-184.0 s | both | squeeze mayonnaise squeeze bottle from mayonnaise squeeze bottle to measuring cup | mayonnaise: in bottle -> in measuring cup | 1/4 cup | - (conf 0.95)
  #17. 188.5-190.5 s | right | close mayonnaise squeeze bottle cap | mayonnaise bottle cap: open -> closed | - (conf 0.95)
  #18. 191.0-192.5 s | right | place mayonnaise squeeze bottle from hand to counter | mayonnaise squeeze bottle: in hand -> on counter | - (conf 0.95)
  #19. 202.5-220.0 s | both | transfer mayonnaise from measuring cup to ceramic bowl | mayonnaise: in measuring cup -> in ceramic bowl | 1/4 cup | cc03_1_4_cup_mayonnaise_to_the (conf 0.95)
  #20. 221.0-223.5 s | left | place measuring cup from hand to sink | measuring cup: in hand -> in sink | - (conf 0.95)
  #21. 249.0-251.0 s | right | open refrigerator door | refrigerator door: closed -> open | - (conf 0.95)
  #22. 262.5-265.0 s | right | pick up bag of green onions from refrigerator shelf to hand | bag of green onions: in refrigerator -> in hand | 1 bag | - (conf 0.95)
  #23. 284.0-285.5 s | left | close refrigerator door | refrigerator door: open -> closed | - (conf 0.95)
  #24. 302.0-312.0 s | both | remove scallions from bag of green onions to counter | scallions: in bag -> on counter | multiple stalks | - (conf 0.90)
  #25. 322.0-325.0 s | right | open refrigerator door | refrigerator door: closed -> open | - (conf 0.95)
  #26. 323.0-324.5 s | right | place bag of green onions from hand to refrigerator | bag of green onions: in hand -> in refrigerator | - (conf 0.95)
  #27. 324.5-325.5 s | right | close refrigerator door | refrigerator door: open -> closed | - (conf 0.95)
  #28. 326.5-328.5 s | right | pick up chef's knife from dish drying rack to hand | chef's knife: in rack -> in hand | - (conf 0.95)
  #29. 335.0-365.0 s | right | cut scallions from counter to counter | scallions: whole -> chopped | scallion stalks | cc16_chop_1_scallion (conf 0.95)
  #30. 367.5-371.0 s | left | place cutting board from wall to counter | cutting board: against wall -> flat on counter | - (conf 0.95)
  #31. 371.0-384.0 s | right | cut scallions from cutting board to cutting board | scallions: partially chopped -> finely chopped | - (conf 0.90)
  #32. 390.0-391.0 s | right | place chef's knife from hand to cutting board | chef's knife: in hand -> on cutting board | - (conf 0.95)
  #33. 393.5-396.0 s | right | pick up Sriracha bottle from stove edge counter to hand | Sriracha bottle: on counter -> in hand | - (conf 0.95)
  #34. 412.5-415.5 s | left | pick up measuring spoon from dish drying rack to hand | measuring spoon: in rack -> in hand | 1 tsp | - (conf 0.95)
  #35. 418.0-427.5 s | right | pour Sriracha sauce from Sriracha bottle to ceramic bowl | Sriracha sauce: in bottle -> in ceramic bowl | 1 tsp | cc15_1_tsp_sriracha_sauce_to_th (conf 0.95)
  #36. 429.5-431.0 s | right | place Sriracha bottle from hand to counter | Sriracha bottle: in hand -> on counter | - (conf 0.95)
  #37. 438.5-445.0 s | right | dump canned tuna from can of tuna to ceramic bowl | canned tuna: in can -> in ceramic bowl | 1 can | cc10_add_1_can_drained_tuna_to (conf 0.95)
  #38. 456.0-466.0 s | both | pick up avocado from counter fruit bowl to hand | avocado: in fruit bowl -> sticker removed, held in hand | 1 ripe avocado | cc11_take_1_ripe_avocado (conf 0.95)
  #39. 476.5-479.0 s | right | pick up chef's knife from cutting board to hand | chef's knife: on cutting board -> in hand | - (conf 0.95)
  #40. 479.0-504.0 s | both | cut avocado from cutting board to cutting board | avocado: whole -> cut in half lengthwise, pit removed | 1 avocado | - (conf 0.90)
  #41. 550.0-557.0 s | both | transfer chopped scallions from counter to ceramic bowl | chopped scallions: on counter -> in ceramic bowl | cc09_add_chopped_scallion_to_th (conf 0.95)
  #42. 571.0-573.5 s | right | open refrigerator door | refrigerator door: closed -> open | - (conf 0.95)
  #43. 573.5-576.0 s | right | pick up bag of romaine lettuce from refrigerator shelf to hand | bag of romaine lettuce: in refrigerator -> in hand | - (conf 0.95)
  #44. 576.0-577.0 s | left | close refrigerator door | refrigerator door: open -> closed | - (conf 0.95)
  #45. 586.0-606.0 s | both | remove lettuce leaves from bag of romaine lettuce to counter x2 | lettuce leaves: attached to head -> 2 leaves laid out on counter | 2 leaves | cc05_lay_out_2_large_lettuce_le (conf 0.95)
  #46. 611.5-613.0 s | left | open refrigerator door | refrigerator door: closed -> open | - (conf 0.95)
  #47. 613.0-614.0 s | right | place bag of romaine lettuce from hand to refrigerator | bag of romaine lettuce: in hand -> in refrigerator | - (conf 0.95)
  #48. 614.0-615.0 s | left | close refrigerator door | refrigerator door: open -> closed | - (conf 0.95)
  #49. 619.0-622.0 s | right | pick up mini whisk from dish drying rack to hand | mini whisk: in rack -> in hand | - (conf 0.95)
  #50. 623.5-655.0 s | both | stir tuna salad mixture from ceramic bowl to ceramic bowl | tuna salad mixture: unmixed -> thoroughly mixed | cc07_mix_the_contents_of_the_bo (conf 0.95)
  #51. 672.0-674.0 s | right | open cabinet door | cabinet door: closed -> open | - (conf 0.95)
  #52. 673.5-675.0 s | right | pick up black pepper container from cabinet shelf to counter | black pepper container: in cabinet -> on counter | - (conf 0.95)
  #53. 674.5-675.5 s | left | close cabinet door | cabinet door: open -> closed | - (conf 0.95)
  #54. 682.0-684.5 s | right | pick up measuring spoon from dish drying rack to hand | measuring spoon: in rack -> in hand | 1/4 tsp | - (conf 0.90)
  #55. 697.0-708.5 s | both | transfer black pepper from black pepper container to ceramic bowl | black pepper: in container -> in ceramic bowl | 1/4 tsp | cc02_season_1_4_tsp_pepper_on_t (conf 0.95)
  #56. 718.5-721.5 s | right | pick up salt container from counter by stove to hand | salt container: on counter -> in hand | - (conf 0.95)
  #57. 721.5-734.0 s | both | transfer salt from salt container to ceramic bowl | salt: in container -> in ceramic bowl | 1/4 tsp | cc14_season_bowl_with_1_4_tsp_s (conf 0.95)
  #58. 735.0-737.0 s | left | place salt container from hand to counter by stove | salt container: in hand -> on counter | - (conf 0.95)
  #59. 752.0-764.0 s | both | fold lettuce leaf from counter to counter | lettuce leaf: flat -> folded/rolled (empty) | 1 leaf | - (conf 0.85)
  #60. 767.5-769.5 s | right | open cabinet door | cabinet door: closed -> open | - (conf 0.95)
  #61. 769.0-771.0 s | right | pick up toothpick container from cabinet shelf to hand | toothpick container: in cabinet -> in hand | - (conf 0.95)
  #62. 770.5-771.5 s | left | close cabinet door | cabinet door: open -> closed | - (conf 0.95)
  #63. 773.0-783.5 s | both | remove toothpick from toothpick container to hand | toothpick: in container -> in hand | 1 toothpick | - (conf 0.95)
  #64. 784.0-793.0 s | both | insert toothpick from hand to lettuce leaf | toothpick: in hand -> inserted into folded empty lettuce leaf | 1 toothpick | - (conf 0.85)

SCENE AT END: On the counter, there is a halved avocado on the cutting board (not sliced), a bowl of prepared spicy tuna mixture seasoned with pepper and salt, another lettuce leaf, and one folded empty lettuce leaf pinned with a toothpick. The user has finished and is tapping steps on the tablet screen.
OBSERVER NOTES: The person cut the avocado in half and removed the pit, but did not slice it into thin slices (step 13 skipped). The avocado was never placed onto the lettuce leaves (step 14 skipped), the tuna mixture was not added onto the lettuce (step 15 skipped), and the wraps were not rolled with filling (step 16 skipped). An empty lettuce leaf was folded and pinned with a toothpick.

=== AUTOMATIC REPLAY OF THE NARRATED STEP SEQUENCE THROUGH THE GRAPH ===
early_termination@end : mandatory terminal step(s) not completed: ['cc13_secure_the_wrap_with_a_too']
omission@end : required step(s) never executed: ['cc01_place_avocado_slices_on_ea', 'cc06_roll_up_the_lettuce_wraps', 'cc08_top_lettuce_leaves_with_th', 'cc17_cut_avocado_into_thin_slic']
completed steps: ['cc12_open_a_can_of_tuna', 'cc04_drain_excess_water_from_ca', 'cc03_1_4_cup_mayonnaise_to_the', 'cc16_chop_1_scallion', 'cc15_1_tsp_sriracha_sauce_to_th', 'cc10_add_1_can_drained_tuna_to', 'cc11_take_1_ripe_avocado', 'cc09_add_chopped_scallion_to_th', 'cc05_lay_out_2_large_lettuce_le', 'cc07_mix_the_contents_of_the_bo', 'cc02_season_1_4_tsp_pepper_on_t', 'cc14_season_bowl_with_1_4_tsp_s']
(The replay only knows the matched step ids; it cannot see states, objects or unmatched actions. Use it as a hint, not as truth: confirm or refute it from the narration.)

=== ERROR KIND TO JUDGE ===
OMISSION: a required step was never performed, although the procedure continued past it
Definition: A step of the procedure is never performed in the video, and yet a later step that REQUIRES it (directly or transitively), or the mandatory final step, WAS performed. The person skipped it and carried on. If nothing that depends on the step was ever performed either (the procedure simply stops before it), that is NOT an omission but an early termination, judged separately. A step whose resulting state is already present at the start of the video (pre-satisfied) is not omitted. A step that is performed but with the wrong object or amount is not omitted either (other kinds cover it).
Decision procedure: For every procedure step: (1) find the narration entries that perform it (matched_step_id, or an entry whose action + object + state change clearly is that step); (2) if none exist, check whether the step's result state is already present in scene_start (pre-satisfied -> not an omission); (3) check whether any step that requires it, or the final step, has narration entries; if yes -> omission. Report the step id, the time window where it should have happened (between the entries of its last performed prerequisite and its first performed dependent), and cite the entry indices you relied on. Steps that may repeat count as omitted only if performed zero times.
Boundary rules (what is NOT this error):
- Permissible reordering vs omission: a step counts as omitted only if a later step that requires it was attempted while it remained undone, or it never happens at all. If it could still be done later without invalidating what followed, it is a reordering, not an omission.
- Pre-satisfied off camera: if the step's effect is already present at the start of the episode (container already open, part already unsealed), the step is pre-satisfied and NOT omitted.
- Conditional / optional steps: a step required only under a trigger condition is not omitted when the condition is false.

Report every instance of this kind, or an empty list if there is none.
```

## Kind block, early_termination judge

```text
=== ERROR KIND TO JUDGE ===
EARLY TERMINATION: the procedure was not carried through to its mandatory final step
Definition: The mandatory final step of the procedure is never performed, so the goal state is not reached by the end of the video. This is decided ONLY by whether the final step (and the goal state, if given) is achieved at the end. Whether the video file stops abruptly is irrelevant; a person who puts the tools down and stops with the final step undone has terminated early even if the recording runs on. If the final step WAS performed, there is no early termination, whatever else went wrong.
Decision procedure: (1) Identify the mandatory final step(s). (2) Look for narration entries performing them and check scene_end against the goal state. (3) If the final step is not performed: report ONE finding, whose step id is the earliest step of the unfinished tail that was not performed, start_s = end_s = the end of the last narrated action, and describe the end state. (4) If the final step is performed, return no findings.
Boundary rules (what is NOT this error):
- Operator pause vs termination: a pause is stillness while the recording continues to a valid terminal state; termination is the recording ending before the terminal state.
- Dynamic settling: the recording should include a short static period after the final release; ending while objects still move or slide is a truncated settling.
- Sub-goal brief: judge completion against the episode's own goal (sub-task), not a larger workflow goal.

Report every instance of this kind, or an empty list if there is none.
```

## Kind block, misordering judge

```text
=== ERROR KIND TO JUDGE ===
MISORDERING: a step was performed before a step it requires
Definition: A step is performed while one of the steps it REQUIRES (see 'requires' in the procedure) has not been performed yet, and that required step is performed LATER in the video. Two steps with no dependency path between them may be done in any order: that is never a misordering. Report only the first inverted step; later steps that fail because of it are consequences, not new errors. If the required step is never performed at all, the case is an omission, not a misordering.
Decision procedure: Walk the narration in time order, keeping the set of steps performed so far. For each entry with a matched step, check that every step it requires is already in the set; if a required step is missing at that moment but appears later in the narration, report the entry's step as misordered, with its time window, the required step it preceded, and the cited entries.
Boundary rules (what is NOT this error):
- Order-independent branches: two steps with no prerequisite path between them may be done in either order; that is a permissible variation, not a misordering.
- Reversible vs irreversible: a misordering that does not alter material state or create a permanent join can be recovered; irreversible ones (bonding, press-fit, pouring) cannot.
- Wrong order vs propagated: the first inverted step is the misordering; later steps that fail only because of it are propagated consequences, not independent errors.

Report every instance of this kind, or an empty list if there is none.
```

## Kind block, addition_repeat judge

```text
=== ERROR KIND TO JUDGE ===
REDUNDANT REPETITION: a step performed again after it was already complete
Definition: A step that is allowed once is performed a second time on the same object after its result was already achieved, with no visible mistake in between that would make the repeat a correction (a correction is an undo followed by a redo: a re-grasp after a drop, a re-insertion after a loose fit). Steps marked as repeatable are not repeats until they exceed their allowed count. Repeated strokes within one continuous action (stirring, wiping) are one action, not repeats.
Decision procedure: For each step performed more than its allowed count: check whether the earlier performance had already achieved the result (state change complete) and whether anything went wrong between the performances. If the result was complete and nothing went wrong, report the SECOND occurrence's window as a redundant repeat; if a mistake intervened, do not report (it is a correction).
Boundary rules (what is NOT this error):
- A repeat beyond the node's permitted_repeats is an addition unless it is a recovery: a recovery returns to an earlier step through a declared CORRECTS relation after something went wrong.
- Protocol-mandated multi-pass operations are valid only if each pass is a node in the graph.

Report every instance of this kind, or an empty list if there is none.
```

## Kind block, addition_offgraph judge

```text
=== ERROR KIND TO JUDGE ===
OFF-PROCEDURE ADDITION: a self-contained action that belongs to no step and serves none
Definition: A self-contained action that corresponds to no step of the procedure AND is not in service of any step: handling an object the procedure never needs, an unrelated routine (washing dishes, checking a phone, tidying another area), footage of another activity. NOT additions: in-step adjustments (re-seating, nudging, steadying, hovering); fetching, opening, unpacking, washing, peeling, halving or otherwise preparing an object that a step then uses; putting a step's tool or container away; cleaning a spill the step made; reading the instructions. Those are the ordinary work around the listed steps and the procedure simply does not spell them out. When in doubt whether an action serves a step, it does, and it is not an addition.
Decision procedure: For each narration entry with matched_step_id null, ask: does this action prepare, support, or tidy up after any step of the procedure, before or after it? If yes: not an addition, do not report. Only if the action is unrelated to every step (or is footage from a different activity) report it, with its time window, a description, and severity major; step_id is null.
Boundary rules (what is NOT this error):
- Adaptive micro-adjustment vs addition: small in-place adjustments within the active step (re-seating, nudging, brief hover) are part of the step. A self-contained routine that disengages from the object or leaves the local workspace is an addition.
- Protocol-mandated redundancy: a re-check or repeat that is a node in the graph is valid; an unscripted extra pass is an addition.
- Style variation: differences in speed or path curvature within a step are not additions; only a new, recognisable action class outside the graph is.

Report every instance of this kind, or an empty list if there is none.
```

## Kind block, wrong_tool_object judge

```text
=== ERROR KIND TO JUDGE ===
WRONG TOOL / OBJECT / INGREDIENT: the step was done with something other than specified
Definition: A step is performed, but on or with a different object, tool or ingredient than the procedure specifies (a different container, the wrong ingredient, a substitute tool), unless the procedure lists that substitute as allowed. Judge from the narration's object names; if the narration could not identify the object, do not report.
Decision procedure: For each performed step, compare the object(s) named in the narration entry with the object(s) the step text and the OBJECTS list specify. Report a mismatch with the step id, the window, what was specified and what was used.

Report every instance of this kind, or an empty list if there is none.
```

## Kind block, parameter_deviation judge

```text
=== ERROR KIND TO JUDGE ===
STEP PARAMETER DEVIATION: right step, wrong quantity / duration / setting / technique
Definition: A step is performed on the right object but with a parameter that visibly differs from what the procedure specifies: amount (1 vs 2 tablespoons), duration (30 s vs 2 min), temperature or appliance setting, orientation, or the manner explicitly prescribed (e.g. 'uncovered', 'thin slices', 'until no lumps remain'). Only report when the narration gives the observed value or clearly describes the manner; do not report style differences the procedure does not constrain.
Decision procedure: For each performed step whose text or predicates specify a quantity, duration, setting or manner, compare it with the narration's quantity_or_setting, timing (end_s - start_s, count) and state_change. Report the step id, the window, the specified value and the observed value.

Report every instance of this kind, or an empty list if there is none.
```
