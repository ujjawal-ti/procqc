# Wrong tool / object / ingredient as its own check (1 Oct 2026)

Code: `procqc/direct/wrongtool.py` (candidates + verifier v1), tests `procqc/tests/test_wrongtool.py`.
Runs: `out/wrongtool_check/{cc4d_egg_round1, cc4d_egg, cc4d_heldout}`. Metrics in the standard format of
`2026-10-01_scorecard.md`.

## Method

A step performed on or with a different tool, container, ingredient or target than the procedure
specifies (EgoPER "Step Modification"). A similar item is still a different item (a bowl is not a
ramekin, hands are not a knife). Not this kind: right item used badly (technique), wrong amount
(parameter), unwashed or unripe right item (unless the step text names that state).

* **Narration and matching**: the cached ones shared with the other checks (match v1).
* **Candidates, one text call**: for every performed step, what the step specifies and what the
  narration says was used: same / equivalent / substitute / not stated. One candidate per substitution:
  the first step where a given specified → used pair appears; later steps with the same pair (the mug
  then used to pour, microwave, top) are listed as `also_steps`, not separate flags.
* **Verifier v1, one video call** on the step's span (padded 2 s, at most 45 s): which item is used in
  the role, specified / equivalent / different.

## Data and gold

CaptainCook4D, 36 recordings with video. The dataset files substitutions under "Preparation Error"
together with spills, unwashed produce, incomplete draining and unopened cans. Gold = Preparation Error
labels whose note describes a substitution ("instead of", "rather than", "with hand", "another bowl",
"not using"), plus one container substitution filed as a Measurement Error ("Take a big cup instead of a
6 Oz ramekin cup"). 22 of the 23 are in the first two recipes, so the split is **egg sandwich (tuning,
13 recordings) vs tuna wraps + Tomato Chutney (held-out, 23 recordings)**. Synthetic data cannot produce
this kind.

## Results (standard scorecard rows)

| split | recordings (with / without) | setting | recording recall | false-alarm rate | recording precision | events TP / FP / FN | of the FP: labelled as another kind | event precision | event recall |
|---|---|---|---|---|---|---|---|---|---|
| tuning, round 1 (no one-flag rule) | 13 (9 / 4) | detector only | 8/9 = 0.89 | 1/4 = 0.25 | 0.89 | 12 / 31 / 5 | – | 0.28 | 0.71 |
| tuning, round 2 | 13 (10 / 3) | detector only | 9/10 = 0.90 | 0/3 = 0.00 | 1.00 | 14 / 2 / 4 | 2 | 0.88 | 0.78 |
| tuning, round 2 | 13 (10 / 3) | detector + verifier | 9/10 = 0.90 | 0/3 = 0.00 | 1.00 | 14 / 0 / 4 | 0 | 1.00 | 0.78 |
| **held-out** | 23 (4 / 19) | detector only | 1/4 = 0.25 | 3/19 = 0.16 | 0.25 | 3 / 3 / 3 | 1 | 0.50 | 0.50 |
| **held-out** | 23 (4 / 19) | detector + verifier | 1/4 = 0.25 | 1/19 = 0.05 | 0.50 | 3 / 1 / 3 | 1 | 0.75 | 0.50 |

Round 1 used the gold rule before the Measurement Error case was added (9 recordings with a
substitution instead of 10). Own cost: $0.011 per recording on tuning, $0.013 on held-out; total spent
$0.84 (round 1 $0.40, round 2 $0.14, held-out $0.30).

**What the held-out numbers mean.** The held-out recipes have only 4 recordings with a substitution.
* Found: 28_45, a soup mug used instead of the bowl. One flag covers the six steps that used the mug,
  including the two the annotators labelled. Caveat: it also covers the step "add chopped scallion",
  whose label is a different substitution (whole scallion), so 1 of the 3 TPs is credited by step only.
* Missed, narration: 15_39, chilli flakes instead of mustard. The narrator wrote "mustard seeds".
* Missed, not visible in narration: 28_50, an unripe avocado; 28_26, scallions partly chopped before the
  cutting board was put down (the narration has both entries; the comparison called it "same").
* The one confirmed false flag (15_28, water poured into the blender for "puree tomatoes without any
  water") is a real error: the annotators labelled it as a Technique Error. The other two candidates
  (a stove knob for "take the pan off the heat") were rejected by the verifier.

On the tuning recipe the remaining misses are 1_34 (stirring with a knife, narration does not say), 1_36
(egg placed on the other muffin piece instead of the lettuce: a target, not an item), 1_49 (bowl and
butter: the narration calls them ramekin and cheese) and 1_143 (cheese bowl labelled on a later step).

## Reading

* The method works where the narration names the item correctly (containers, hands instead of a knife):
  tuning precision 1.00 with the verifier, recall 0.78.
* Its limit is the narration: the narrator sees the procedure's vocabulary and sometimes writes the
  expected item (mustard, ramekin, cheese) instead of the one used. A per-step video question for steps
  that name a specific item (the agreed plan: "wrong tool targeted per-step question") would not depend
  on the narration; it costs one clip per such step (about 8 per recipe).
* Held-out has 4 positives: too few to estimate recall; it mainly shows the false-alarm rate (1/19 with
  the verifier).

## v2: per-step frame check, no narration for identity (2 Oct 2026)

Code: `procqc/direct/wrongtool_v2.py`, tests `procqc/tests/test_wrongtool_v2.py`. Runs:
`out/wrongtool_check/{v2_crops_egg, v2_frames_egg, v2_frames_heldout}`. All frame calls go through Fuelix,
gemini-3.8-flash, reasoning effort low. The narration is used only for step timing.

* **Item cards, one text call per graph**: for each step, the item in each role (tool, container,
  ingredient, target), with a neutral role description, the expected appearance and look-alikes.
  Appliances are skipped. One check per distinct item, at the first step that uses it; other steps
  naming the same item are listed as `also_steps`.
* **Describe, blind**: 6 frames from the step window. The step text is shown with the expected item
  masked, and the model names what fills the role.
* **Compare, text only**: is the described item the specified one, an equivalent, or different.
* Two evidence settings. **Crops**: the model first boxes the item, the crop is enlarged and its size is
  given relative to the hand. **Frames**: no boxing; the 6 full frames are described.

| split | recordings (with / without) | setting | recording recall | false-alarm rate | recording precision | events TP / FP / FN | of the FP: labelled as another kind | event precision | event recall | own cost / rec |
|---|---|---|---|---|---|---|---|---|---|---|
| tuning | 13 (10 / 3) | v1 (narration) + verifier | 9/10 = 0.90 | 0/3 = 0.00 | 1.00 | 14 / 0 / 4 | 0 | 1.00 | 0.78 | $0.011 |
| tuning | 13 (10 / 3) | v2 crops | 10/10 = 1.00 | 2/3 = 0.67 | 0.83 | 12 / 8 / 6 | 6 | 0.60 | 0.67 | $0.081 |
| tuning | 13 (10 / 3) | v2 frames | 10/10 = 1.00 | 1/3 = 0.33 | 0.91 | 16 / 5 / 2 | 4 | 0.76 | 0.89 | $0.048 |
| **held-out** | 23 (4 / 19) | v1 (narration) + verifier | 1/4 = 0.25 | 1/19 = 0.05 | 0.50 | 3 / 1 / 3 | 1 | 0.75 | 0.50 | $0.013 |
| **held-out** | 23 (4 / 19) | v2 frames | 3/4 = 0.75 | 11/19 = 0.58 | 0.21 | 4 / 22 / 2 | 7 | 0.15 | 0.67 | $0.069 |

v2 is one check with no separate verifier. Every flag came back with a self-reported confidence of
0.85 or more, so the 0.6 review threshold separated nothing. Spend: crops tuning $1.05, frames tuning
$0.62, frames held-out $1.59, plus about $0.23 of smoke tests.

**Crops were worse than full frames at 360p.** Boxing a role ("what the hand uses to cut") often landed
on the object being acted on (the bread), and the crop then lost the hands. Full frames were cheaper,
faster (p50 16 s vs 28 s) and more accurate. Localisation may still help at full resolution; the
local videos are 640x360.

**What v2 fixes.** It finds items the narration got wrong: butter instead of cheese (1_49), red pepper
flakes instead of mustard (15_39), bare hands instead of a knife in 4 more egg recordings. Held-out
recording recall rises from 1/4 to 3/4.

**Why it fails on held-out.** There were 24 held-out flags. Two are the true finds above (15_39 and
the mug in 28_45). The other 22 fall into five groups:
1. **Wrong moment, 10 flags.** The frames show a different action from the step: mustard seeds or
   water for "add tomato puree", an onion for "take a tomato", a bowl of tuna or a measuring spoon for
   "take a ripe avocado", an empty spoon for cumin. Step timing comes from the narration match, and
   the describer names whatever is in hand. Salt read as dried herbs (28_25) is also here.
2. **Same item, different form, 4 flags.** Chopped, crushed or chunky tomatoes for "tomato puree". If
   it is an error at all, it is an under-pureed technique error, not a substituted item.
3. **Wrong role, 3 flags.** A measuring cup or spoon named as the "bowl": the describer reported the
   item carrying the ingredient, not the vessel it goes into.
4. **Generic name, 3 flags.** "Hot sauce" for Sriracha. At 360p a brand cannot be told apart, so the
   describer gives the category and the compare call treats the category as a substitute. One of the
   three (28_44) says the sauce came from a glass bottle; that may be a real, unlabelled substitution.
5. **Plausible but unlabelled, 2 flags.** A cake pan (15_28) and a ramekin (15_4) used as the serving
   bowl.

On tuning, the remaining false flags fit groups 1 and 4 too: "egg carton" for pouring the egg (1_143),
"bread roll" for the English muffin (1_36), "English muffin" as the target (1_49) and "spinach" for
lettuce (1_34, 1_37). The extracted frames could not show which leaf it was at 360p.

## Reading (v1 vs v2)

* v1 is precise but blind to anything the narrator writes in the procedure's own vocabulary. v2 sees
  those cases but flags far too often on a new recipe: 11 of 19 clean recordings.
* The fixes the failure groups point to are about the question, not resolution. The check should
  confirm that the step's action is visible before naming the item (group 1). Compare should have
  "same item, different form" and "category only, cannot tell" outcomes that do not count as a
  substitution (groups 2 and 4). The role question should name the receiving vessel (group 3). A
  confirmed flag needs a second, independent look, since the self-reported confidences carry no signal.

## v3: form and category outcomes, another step's item, second look (3 Oct 2026)

Code: `procqc/direct/wrongtool_v3.py`, tests `procqc/tests/test_wrongtool_v3.py`. Runs:
`out/wrongtool_check/{v3_egg, v3_heldout}`. v1 and v2 are unchanged. Each change answers one v2 failure
group:

* **Cards** also give the base item and the form the step names ("tomato" / "puree"). Containers are
  described as the vessel the contents end up in. No card is made for an item a step says not to use.
* **Blind look** (6 frames of the step) also reports whether the moment of the action is seen, how
  precisely the object can be identified (exact or only a category), its form, and any other objects
  in the role. Measuring cups and spoons are described as transfer tools. A first smoke test made "the
  moment is seen" a hard gate. That lost 6 of 11 items, the real chilli-flakes case among them, since a
  spoonful is added between frames. The gate was dropped, and the timing question was left to the
  second look.
* **Compare** has two more outcomes that are not substitutions: *same item, other form* (kept as a
  note for the technique check) and *category only* (the observer's category contains the specified
  item and nothing rules it out).
* **Another step's item, in code.** If every word of another step's base item is in the observed name
  (mustard seeds while checking "add tomato puree"), the flag goes to review, not confirmed.
* **Second look, non-blind**: 10 frames over the step ±8 s. Is the step's action seen, is the specified
  item used for it at any point, and what is used. Statuses: *substitute* goes to confirmed (or review,
  if it is another step's item); *specified used* or *form only* goes to rejected; otherwise review.
  Self-reported confidences are not used.

| split | recordings (with / without) | setting | recording recall | false-alarm rate | recording precision | events TP / FP / FN | of the FP: labelled as another kind | event precision | event recall | own cost / rec |
|---|---|---|---|---|---|---|---|---|---|---|
| tuning | 13 (10 / 3) | v1 + verifier | 9/10 = 0.90 | 0/3 = 0.00 | 1.00 | 14 / 0 / 4 | 0 | 1.00 | 0.78 | $0.011 |
| tuning | 13 (10 / 3) | v2 frames | 10/10 = 1.00 | 1/3 = 0.33 | 0.91 | 16 / 5 / 2 | 4 | 0.76 | 0.89 | $0.048 |
| tuning | 13 (10 / 3) | v3 detector only | 7/10 = 0.70 | 0/3 = 0.00 | 1.00 | 9 / 2 / 9 | 2 | 0.82 | 0.50 | $0.063 |
| tuning | 13 (10 / 3) | v3 + second look | 5/10 = 0.50 | 0/3 = 0.00 | 1.00 | 7 / 0 / 11 | 0 | 1.00 | 0.39 | $0.063 |
| **held-out** | 23 (4 / 19) | v1 + verifier | 1/4 = 0.25 | 1/19 = 0.05 | 0.50 | 3 / 1 / 3 | 1 | 0.75 | 0.50 | $0.013 |
| **held-out** | 23 (4 / 19) | v2 frames | 3/4 = 0.75 | 11/19 = 0.58 | 0.21 | 4 / 22 / 2 | 7 | 0.15 | 0.67 | $0.069 |
| **held-out** | 23 (4 / 19) | v3 detector only | 2/4 = 0.50 | 11/19 = 0.58 | 0.15 | 4 / 14 / 2 | 6 | 0.22 | 0.67 | $0.072 |
| **held-out** | 23 (4 / 19) | v3 + second look | 2/4 = 0.50 | 2/19 = 0.11 | 0.50 | 4 / 2 / 2 | 2 | 0.67 | 0.67 | $0.072 |

Spend: smoke tests $0.30, tuning $0.82, held-out $1.66. Two held-out recordings (15_33, 15_39) reused
the smoke test's answers, so the held-out cost per recording is about $0.078 when the smoke spend is
included. v2's third held-out recording "found" (28_26) came from a flag on another step (a measuring
cup); event recall is the same for v2 and v3 (4 of 6).

**Held-out: the false alarms are mostly gone.** With the second look, 2/19 clean recordings are flagged
(v2: 11/19). Both real substitutions found by v2 are still found: red pepper flakes instead of mustard
(15_39) and the mug used as the bowl (28_45). Of the 16 candidates, the second look confirmed 4,
rejected 7 (salt, the onion bag, the hot sauce, water, a red paste, a pot, mayonnaise) and sent 5 to
review (mustard seeds at the puree step, caught by the other-step rule; the cake pan; a measuring spoon;
black pepper for salt; tuna at the avocado step). The two it confirmed wrongly:
* 15_37, "saucepan instead of a pan": too strict. The card described a shallow pan, and the second
  look accepted that. The step only says "a pan".
* 15_46, "dried herbs instead of cumin seeds": the second look describes green flakes scooped from a
  spice container. It may be a real, unlabelled substitution.
Both are on steps the annotators labelled with another kind (order and amount).

**Tuning: recall fell, from a wording problem in the cards.** All 5 "bare hands instead of a knife"
cases were lost. This time the card described the knife's role as "what the hand grips to slice
through the bread". That assumes an object is held. When the bread was split by hand, the blind look
found nothing gripped and answered "not visible". v2's card said "what the hand uses to cut", and that
was enough to get "bare hands". The other losses are the trade the category outcome makes:
* 1_28: the dish was called a "ramekin", so the bowl in its place was not flagged.
* 1_34 and 1_43: "small bowl" at category level became "category only". The annotators labelled neither
  bowl, so these two are correct against gold.
* 1_36: the mug's second look was "unclear", so the flag went to review.

**Next fix (not run).** The role wording must not assume an object exists ("what the cutting is done
with", not "what the hand grips"), and the blind look should answer "bare hands" or "none" when no
object is used. The card should also not narrow a general item ("a pan") to one type in its appearance.

## v4: v3's method with general prompts (3 Oct 2026)

Code: `procqc/direct/wrongtool_v4.py` (prompts only; the method is v3's, which now takes a prompt set and
runs unchanged with its own). Tests: `procqc/tests/test_wrongtool_v4.py`. Run: `out/wrongtool_check/v4_egg`.

**Why.** procqc is for any demonstration data, not for this benchmark. v2 and v3's prompts used the
evaluation recipes' own items as examples. Some came from held-out failures: chilli flakes vs mustard
seeds (v2, from v1's held-out miss), and tomato puree, Sriracha and hot sauce (v3). That tunes the check to
these recipes and makes their held-out numbers optimistic. v4 states each rule as a general principle,
with examples from other domains (screwdriver, coin, panel, beaker, gripper). A test fails if any item of
the three evaluation recipes appears in v4's prompts.

**Fixes, each a general principle:**
* A role description must not assume an object is used or held ("what the cutting is done with", not
  "what the hand grips to cut").
* The blind look may answer "bare hand" or "gripper only".
* A card is exactly as general as the step: "a container" covers every container.

| split | recordings (with / without) | setting | recording recall | false-alarm rate | recording precision | events TP / FP / FN | of the FP: labelled as another kind | event precision | event recall | own cost / rec |
|---|---|---|---|---|---|---|---|---|---|---|
| tuning | 13 (10 / 3) | v3 detector only | 7/10 = 0.70 | 0/3 = 0.00 | 1.00 | 9 / 2 / 9 | 2 | 0.82 | 0.50 | $0.063 |
| tuning | 13 (10 / 3) | v3 + second look | 5/10 = 0.50 | 0/3 = 0.00 | 1.00 | 7 / 0 / 11 | 0 | 1.00 | 0.39 | $0.063 |
| tuning | 13 (10 / 3) | v4 detector only | 9/10 = 0.90 | 0/3 = 0.00 | 1.00 | 12 / 5 / 6 | 4 | 0.71 | 0.67 | $0.080 |
| tuning | 13 (10 / 3) | v4 + second look | 7/10 = 0.70 | 0/3 = 0.00 | 1.00 | 11 / 0 / 7 | 0 | 1.00 | 0.61 | $0.080 |

Spend $1.04. The general card prompt writes more cards (8-11 items per recording, v3: 7-9), so it costs
more than estimated.

* All 5 bare-hand cases are found again; none of the prompts names a knife or bread.
* Nothing is confirmed wrongly (event precision 1.00 with the second look), with no recipe items in the
  prompts.
* Of the 5 unconfirmed flags, 3 went to review by the other-step rule (an egg patty, a muffin half, a
  cheese stick: items of other steps). In 1_34 the egg was placed on the muffin half instead of the
  lettuce. That is the same error the annotators labelled in 1_36, but it is not labelled in 1_34. The
  mug in 1_36 went to review because the second look did not see the coating.
* Still missed: the bowl in 1_28, the stirring knife in 1_34, and the later-step labels in 1_143.

Held-out has not been run with v4. It has now been looked at twice (v2, v3), so it is a weaker test
than it was. The real test of these principles is data the method has never seen.

## v4: narration timing vs annotator timing (4 Oct 2026)

**Purpose:** measure detection on its own, with reference step boundaries instead of the narration's.
* `python3 -m procqc.audit.opensource_cc4d step-times` writes `out/opensource/captaincook4d/step_times.jsonl`.
  It holds only the annotators' step boundaries, matched to our step ids by step text. No error tags,
  notes or modified descriptions are written.
* With `--step-times FILE`, v3 and v4 take step windows from that file and do not use the narration at
  all. The file format is general (episode id, step id, start and end), so internal data with annotated
  steps can use it as well.
* Runs: `out/wrongtool_check/{v4_egg_anntime, v4_heldout_anntime, v4_heldout}`.

| split | recordings (with / without) | timing | setting | recording recall | false-alarm rate | recording precision | events TP / FP / FN | of the FP: labelled as another kind | event precision | event recall | own cost / rec |
|---|---|---|---|---|---|---|---|---|---|---|---|
| tuning | 13 (10 / 3) | narration | detector only | 9/10 = 0.90 | 0/3 = 0.00 | 1.00 | 12 / 5 / 6 | 4 | 0.71 | 0.67 | $0.080 |
| tuning | 13 (10 / 3) | narration | + second look | 7/10 = 0.70 | 0/3 = 0.00 | 1.00 | 11 / 0 / 7 | 0 | 1.00 | 0.61 | $0.080 |
| tuning | 13 (10 / 3) | annotator | detector only | 9/10 = 0.90 | 0/3 = 0.00 | 1.00 | 12 / 1 / 6 | 1 | 0.92 | 0.67 | $0.073 |
| tuning | 13 (10 / 3) | annotator | + second look | 8/10 = 0.80 | 0/3 = 0.00 | 1.00 | 12 / 0 / 6 | 0 | 1.00 | 0.67 | $0.073 |
| held-out | 23 (4 / 19) | narration | detector only | 2/4 = 0.50 | 14/19 = 0.74 | 0.12 | 4 / 21 / 2 | 11 | 0.16 | 0.67 | $0.080 |
| held-out | 23 (4 / 19) | narration | + second look | 2/4 = 0.50 | 1/19 = 0.05 | 0.67 | 4 / 1 / 2 | 0 | 0.80 | 0.67 | $0.080 |
| held-out | 23 (4 / 19) | annotator | detector only | 1/4 = 0.25 | 8/19 = 0.42 | 0.11 | 0 / 11 / 6 | 6 | 0.00 | 0.00 | $0.080 |
| held-out | 23 (4 / 19) | annotator | + second look | 0/4 = 0.00 | 2/19 = 0.11 | 0.00 | 0 / 2 / 6 | 1 | 0.00 | 0.00 | $0.080 |

The narration-timed cost excludes the shared narration ($0.013 per minute of video). Spend: $0.95 + $1.83
+ $1.84.

**v4 on held-out with narration timing.** This is the first held-out run with general prompts. It does at
least as well as v3, whose prompts contained held-out items: false alarms 1/19 (v3: 2/19), events 4/1/2.
The remaining confirmed false alarm is "saucepan instead of a pan" (15_4). The rule that a general item
covers every type of it did not stop it.

**Annotator timing did not isolate detection: it changed what the frames sample.** Annotator steps are
about 4 times longer than the narration's matched entries. The median window was 41 s against 11.5 s on
held-out, and 40.5 s against 7.7 s on tuning. The check always samples 6 frames, so on a 42 s step they
are about 7 s apart.
* Items that stay in view for the whole step (the mug or bowl being coated, the hands splitting the
  muffin) are seen either way. On tuning, annotator timing was slightly better: events 12/0/6 against
  11/0/7, and fewer false candidates (1 against 5).
* Items used for a moment are missed. The spoonful of red pepper flakes (15_39) became "seeds, category
  only". In the 40 s window of the Sriracha step (28_45), the bowl was in view and the mug was not. Both
  real held-out finds were lost.

**What this means.** Detection depends on looking at the moment the item is used, not just on knowing
the step's boundaries. A fixed number of frames per step suits short windows only. The general fix is
two stages: first find the moment of the action within the step (many small frames, which are cheap),
then describe the item at that moment at full resolution. That works with either timing source. With it,
annotator timing would become a fair test of detection alone. Not built yet.

## Status (4 Oct 2026): not working

The frame-based check (v2-v4) does not reliably detect wrong tools, objects or ingredients.
* On held-out data it finds 2 of 4 recordings with a substitution. With 4 positives that number says
  almost nothing.
* Its precision comes from the second look; the first stage flags 14 of 19 clean recordings.
* Better step timing (the annotators') dropped it to 0 of 4. A detector that works only when its 6 frames
  happen to land on the moment of use is not detecting reliably.
* v2-v4 were developed against the same 36 recordings, and the held-out recipes have been looked at three
  times. The numbers above are optimistic, not conservative.
Nothing here shows the method works on unseen data. No further variants are being built until it is
decided whether to measure the frozen check once on an untouched set, rethink the design, or park the kind.

## v5: find the moment, zoom, closed question (5 Oct 2026)

Design from `docs/research/2026-10-04_wrong_tool_detection_methods.md`, code in
`procqc/direct/wrongtool_v5.py`. All calls use Fuelix gemini-3.8-flash.
1. **Moment.** Frames at 2 per second over the annotator step span (up to 32), as numbered contact
   sheets. The model picks the tiles where a hand or gripper uses something in the step's role.
2. **Zoom.** Full-resolution frames at 4 per second around those tiles (up to 6). One box around the hand
   and the object on 2 of them, cropped and enlarged.
3. **Identify.** A closed question: the specified item, up to 4 look-alikes, "bare hand or gripper",
   "other (name it)", "cannot tell". The specified item is not marked. Asked up to 3 times, with the
   options shuffled each time. It stops early when two answers agree on the specified item.
4. **Decide.** Majority on another item, or "other" judged different / another form, gives a candidate.
   It is *confirmed* only if all 3 asks agree and the item is not another step's item. Otherwise it is
   *needs review*. Fuelix returns no answer probabilities, so agreement is the only confidence.

**Gold** (fixed 5 Oct, before the test run): Preparation Error notes classified as a wrong item by
`procqc/audit/cc4d_prep_taxonomy.py`. Hard ingredient swaps stay in, a different form counts as a
different item, and cherry tomato and tomato count as the same item. The other Preparation Errors are
listed in `docs/taxonomy/2026-10-05_cc4d_preparation_errors_not_wrong_tool.md`.

**Data.**
* Development: the 13 egg-sandwich recordings already used for v2-v4.
* Test: 44 recordings from 20 recipes that no version had seen (4.0 GB): 24 with a wrong item
  (78 labelled events) and 20 with none. Step timing came from the annotators, for both sets.
* The code was frozen after the development run with no changes (hashes in
  `out/wrongtool_check/v5_test_anntime/frozen_code.sha256`) and run once on the test set.
* In 2_26, one annotated step ("Microwave for 1.5 minutes") is not in the task graph, so it was never
  checked.

| split | setting | recording recall | false alarms | recording precision | events TP / FP / FN | event precision | event recall | cost / recording |
|---|---|---|---|---|---|---|---|---|
| development (13) | candidates | 8 / 9 | 2 / 4 | 0.80 | 12 / 3 / 5 | 0.80 | 0.71 | $0.17 |
| development (13) | confirmed (3/3) | 7 / 9 | 0 / 4 | 1.00 | 11 / 1 / 6 | 0.92 | 0.65 | $0.17 |
| **test (44)** | candidates | 22 / 24 | 13 / 20 | 0.63 | 39 / 49 / 39 | 0.44 | 0.50 | $0.24 |
| **test (44)** | confirmed (3/3) | 16 / 24 | 8 / 20 | 0.67 | 24 / 29 / 54 | 0.45 | 0.31 | $0.24 |

For comparison, v4 with annotator timing scored the same development set at 7 / 9, 1 / 4 false alarms,
events 11 / 1 / 6 (taxonomy gold). v4 was not run on the test set. Spend: smoke $0.64, development
$2.24, test $10.57.

### Status (5 Oct 2026): not working on unseen recipes

Development and test disagree badly. On development, no clean recording was flagged. On unseen recipes,
8 of 20 clean recordings were flagged, and fewer than half of confirmed flags are right. Recall rose
(16 of 24 recordings, against 0-2 of 4 for v4 on held-out), so finding the moment does help perception.
But a QC check that sends back 40 % of good recordings is not usable.

**Why the 29 wrong confirmed flags happened** (read from the flag text, not checked against video):

| cause | flags | examples (specified → named) |
|---|---|---|
| Same item named more specifically, a variety, or a synonym, judged "different" | 19 | sieve → colander, scissors → kitchen shears, cherry → grape tomatoes (2), cremini → white button mushrooms (2), Italian herbs → dried oregano, marinara → pizza sauce, cup → mug, small bowl → ramekin, platter → dinner plate, mixture → "bruschetta topping mix" (2) |
| A carrier or measuring tool named for a container role | 4 | bowl → measuring spoon, bowl → measuring cup, mushroom stems → drawer |
| A different item named, not labelled (perception error or a missed label) | 5 | lime → lemon juice, minced ginger → salt, mozzarella → parmesan |
| The same flag as a labelled error in another recording of the recipe | 1 | 10_6 spoon for butter knife (labelled in 10_31) |

* The main failure is no longer perception. It is the decision of whether two names are the same item.
  The egg recipe hardly tests this, because its swaps are coarse (bowl for ramekin, hand for knife).
  Unseen recipes name specific ingredients and tools, and the model's name for what it sees rarely
  matches the step's wording.
* Some cases are genuinely ambiguous without a policy (cremini against white button mushrooms is a
  variety, like cherry tomato against tomato). The check needs an explicit equivalence rule, not a model
  judgement made per step.
* Several false flags repeat across recordings of the same recipe (cremini 23_16 and 23_41, the
  bruschetta mixture 29_17 and 29_18, standard mug 9_8 and 9_13). In 9_8 the same flag is labelled; in
  9_13 it is not. Some of these are label inconsistency, not detector errors.

**Misses (54 events).** 31 of them come from 6 recordings that each carry 6 or more labels (one
substitution labelled at every step that used it, such as "mug instead of a bowl" on 3 steps of 7_44).
Of the rest, the common types are:
* a container in the target role ("bowl instead of plate", "mug instead of mixing bowl");
* a bare hand used instead of a utensil, for stirring or whisking;
* an ingredient swap that looks alike (sugar for salt, baking soda for powder, vegetable oil for olive oil).
Several were found but left as needs review: zucchini 2/3, green bell pepper 3/3 (another step's
item), bowl for plate 3/3, baking soda 2/3.

**Options, not yet built or run.**
1. Replace the free-text compare with a fixed equivalence rule: same base item at any variety, size or
   synonym is the same; only a different base item, or a different form, is flagged. The base item
   would come from the item card, not from the observed name. This targets 19 of the 29 false flags.
2. Treat a substitute that recurs in most recordings of the same task as "check the specification",
   not as an operator error. This is general for fleet data, but it needs several recordings per task.
3. Measure any change on a fresh split, not this test set, which has now been looked at once.

## v6: relation rule, a check at every step, implied tools (5 Oct 2026)

Code in `procqc/direct/wrongtool_v6.py`. Version 6 keeps version 5's moment, zoom and closed question,
and changes three things:
1. **Relation rule.** A non-specified answer gets one fixed relation to the specified item: same, kind_of,
   broader, not_in_role, sibling, other_form or different. A text-only call answers that question about
   the two names. A fixed rule then decides:
   * same, kind_of and not_in_role are not flagged;
   * broader is flagged only when the model picked a listed look-alike over the specified item;
   * sibling, other_form and different are flagged.
   No item list or map is kept; the relation is worked out for each new pair.
2. **A check at every step**, not once per item. Flags of the same substitute are reported as one finding.
3. **Implied tools.** Steps get item cards for tools the action needs but the step does not name, kept
   general ("a mixing utensil").

Sibling policy (user decision, 5 Oct 2026): another variety of the same item is flagged as an error.

Only two things have run so far. The full benchmark has not.

### 1. The relation rule alone, on version 5's saved answers

This applies the rule to version 5's stored answers (text calls only, about $0.05). It keeps version 5's
checked steps and step coverage, so only the rule changes. The test set has now been looked at in
detail, so these are development numbers.

| set | decided by | recording recall | false alarms | events TP / FP / FN | event precision |
|---|---|---|---|---|---|
| egg (13) | v5 compare | 7 / 9 | 0 / 4 | 11 / 1 / 6 | 0.92 |
| egg (13) | v6 relation rule | 7 / 9 | 0 / 4 | 11 / 1 / 6 | 0.92 |
| test (44) | v5 compare | 16 / 24 | 8 / 20 | 24 / 29 / 54 | 0.45 |
| test (44) | v6 relation rule | 14 / 24 | 7 / 20 | 22 / 21 / 56 | 0.51 |

**Verdict: a small cleanup, not a fix.** Recording recall fell from 16/24 to 14/24, and events found
from 24 to 22. False alarms fell by one recording, from 8/20 to 7/20. About half of the confirmed flags are
still wrong. (Before the run this rule was said to target 19 of the 29 wrong flags. It removed 8.)
* **Why the recall fell.** In 26_46 and 2_42, version 5's only flag was a wrong one (the shears, the
  ramekin), and the labelled errors in those recordings were not found by either version. In 10_31, the
  peanut-butter flag had covered two steps labelled for the utensil. So both versions really find 14 of
  24 recordings; the rule found nothing new.
* **The 8 wrong flags it removed:** scissors → kitchen shears, cup → mug, small bowl → ramekin, chopped
  pepper → diced pimiento, nut butter → peanut butter, the "mixture" (2), bowl → measuring spoon. One
  clean recording (27_4) is no longer flagged.

**It does not fix all the equivalence problems.** The 21 wrong confirmed flags left:

| cause | flags | cases |
|---|---|---|
| sibling, flagged by the policy, not labelled by CaptainCook4D | 10 | cherry → grape tomatoes (2), cremini → white button mushrooms (2), platter → dinner plate, wooden spoon → wooden spatula, fish slice → wooden spatula, skillet → saucepan, marinara → pizza sauce, large → standard mug (labelled in 9_8, not in 9_13) |
| the relation call broke its own definitions | 6 | sieve → colander and Italian herbs → oregano (should be kind_of); pieces of chocolate → chocolate chips (called other_form); bowl → measuring cup, mushroom stems → drawer, jar → squeeze bottle (should be not_in_role) |
| a different item named, not labelled (perception error or missed label) | 4 | lime → lemon juice, minced ginger → salt, mozzarella → parmesan, sweet-and-sour → hot sauce |
| labelled in another recording of the recipe | 1 | 10_6 spoon for butter knife |

* Under the user's policy, the 10 sibling flags are correct flags that the annotators did not label. The
  scorecard counts them as false, because the gold comes from CaptainCook4D's labels.
* The 6 relation mistakes are a model error in the new stage: one call per pair. Asking 3 times, as the
  identify stage does, or adding more definitions with examples are the obvious options. Neither has
  been tried.

### 2. Full version 6 smoke test (2 development recordings, $0.69)

| recording | gold | version 6 confirmed | version 5 confirmed (same recordings) |
|---|---|---|---|
| 1_42 | bowl for ramekin, oil for cooking spray, hands for knife | bowl for ramekin (coat step, covering 3 more steps), bare hand for knife | all 3 |
| 1_7 | none | none (1 needs review: a mug while stirring) | none |

* **The checks run end to end.** Each recording got about 20 checks, against about 10 for version 5, at
  $0.35 per recording against $0.32.
* **A tool the step does not name was checked as designed.** A fork used for stirring passed as a kind of
  "a mixing utensil".
* **Oil for cooking spray was missed.** The moment stage did not find the spraying this time. That stage
  varies between runs, and checking every step does not remove that.
* **The pour step ("bowl instead of ramekin") was not seen.** Version 5 got credit there only through a
  flag at another step.

## Would two views help? Free frame check (11 Oct 2026)

Six labelled substitutions that version 5 missed on the unseen recipes (annotator step times), chosen so
that seeing could be the problem. Frames at 25 / 50 / 75 % of each annotated step, plus a 3x crop of the
work area by hand; `out/wrongtool_check/frame_check_twoview/`. The saved version 5 answers were read for each.

| recording | label | full frame (640x360) | crop | why version 5 missed it |
|---|---|---|---|---|
| 10_50 | knife instead of floss | knife clearly visible | not needed | step never checked (floss was checked at two other steps) |
| 18_31 | cheddar instead of parmesan | bag label readable ("Extra Sharp Cheddar") | not needed | step never checked |
| 7_48 | spoon instead of whisk | hand covers the utensil | still covered | step never checked |
| 22_30 | metal spatula instead of wooden spoon | camera faces the microwave; the stirring is out of view | no help | moment stage found nothing |
| 3_36 | vegetable oil instead of olive oil | bottle visible, label unreadable | bottle clearer, label still unreadable | 3 / 3 answers "cannot tell", citing the label |
| 16_26 | sugar instead of salt | small red bag | white granules from a paper bag | 1 of 3 answers said sugar; the 3 / 3 rule needs all three |

* **Two views would have fixed none of the six.** Version 5 already sends zoomed crops next to the frames
  (6 frames, 2 crops per check), so it is a two-view design already.
* **The main cause is coverage: 3 of 6 steps were never checked.** Version 5 checks each item at a few
  steps only. Version 6 checks every step, which targets this.
* **One case needs more resolution, not a crop.** At 360p the oil label can't be read even upscaled.
  Internal data (1440x1080 per eye) would make crops useful for cases like this.
* **One case is the agreement rule.** The right answer appeared once in three asks.
* Our CaptainCook4D copy is video only, so sensor signals can be tried on internal data only.
