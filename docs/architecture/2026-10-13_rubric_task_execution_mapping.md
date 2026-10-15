# Snowbird "Task Readiness & Execution": what our taxonomies already cover (13 Oct 2026)

Source: `meta_video_samples/Copy of Snowbird Quality Rubric.pdf`. How often reviewers flag each parameter, from the
final review of 50,562 recordings on the FTS workflow:

| Parameter | Medium | Discard |
|---|---|---|
| task_specific_requirements | 8.8 % | 2.0 % |
| scene_state | 4.2 % | 0.4 % |
| task_efficiency | 1.9 % | 0.3 % |
| navigation_manipulation | 1.4 % | 0.1 % |
| object_handling | 0.6 % | 0.02 % |
| object_grouping | 0.3 % | 0.04 % |
| lighting (same section, not in the list) | 10.6 % | 0.3 % |

## One shared log, many rules

Every check below is a rule over one per-recording log, plus a frame check only where a rule fires (as in
gestural anchoring). All four parts exist; pick/place events are a first version.

| Log part | Source | Status on internal data |
|---|---|---|
| Body events: walk, bend, grip, still, places visited, gestures | sensor log (`Physical AI/procqc`, `signals.sensors`) | built; grip closure is unreliable |
| Item log: each item, where it was first seen, when last handled, where it ended | early-termination check (`direct/termination_v2.py`) | built; times read at 2 fps |
| Steps matched to graph nodes | narration arm (`direct/narrate_judge.py`) | run on 11 internal recordings at 5 fps, $0.037 each |
| Pick/place events per item (who picked what, when, where to) | `signals/pickplace.py`: narration entries matched to the graph's pick-up and put-down steps, with the sensor walk/bend at each event | v1, 11-recording pilot: 8 of 11 give one pick and one place per item; the other 3 are grouped carries named as a group. Frames not checked yet |

## Mapping

| # | Rubric parameter | Rubric definition (short) | Existing taxonomy that covers it | Covered today | Change needed | Effort |
|---|---|---|---|---|---|---|
| 1 | Task-Specific Requirements | every checklist requirement followed; discard = a critical one missed | omission, misordering, early termination, wrong destination, parameter (counts) | **most of the critical part** | criticality per graph node; SOP "Constraints / Avoid" check; severity → score | medium |
| 2 | Task efficiency | no unnecessary trips; pick up items in the path | repeat (partly) | **little** | trip log: walks between places × items carried | medium |
| 3 | Navigation and manipulation | finish pick/place before walking | none | **none**, but the sensors have the signal | walk overlapping a bend or grip → candidate | low |
| 4 | Object handling | directly to destination; set down, no toss or drop; hands only | wrong destination, wrong object | **destination and object only** | drop/toss and body-part detection; "moved twice" from the item log | medium to high |
| 5 | Scene state | plausible locations, realistic mess, not staged | off-graph addition (other room only) | **little** | scene-scope profile per client; staged-layout question on the first frames | medium |
| – | Object grouping | medium/large one at a time; small ones grouped | none | none | falls out of the trip log in 2 | low after 2 |
| – | Lighting | hands, objects and room clearly visible | none | none | brightness and contrast per frame, free | low |
| – | Gestural anchoring (recording_start, recording_end; own rubric attribute) | two thumbs up right before and right after the task | gestural anchoring, built on early termination | **discard: yes; medium: no** | medium needs a different signal than the time gap | done; see [report](../benchmarks/2026-10-13_gestural_anchoring_check.md) |

## Per parameter

**1. Task-Specific Requirements.** This is graph against narration, as you said. Our checks already report what
reviewers call critical: a missing required step (omission), a broken dependency (misordering), an unfinished
goal (early termination), items in the wrong place (wrong destination), a wrong count (parameter).
* Missing: (a) which requirements are critical and which are minor. Tag each graph node when the graph is drafted.
  Final placement and the goal are critical; "stand still for 1 second" is minor. (b) No check reads the SOP's
  "Constraints / Avoid" lines. (c) A rule: any critical finding → discard, minor findings only → medium.
* Cheap win: SOP micro-steps such as "walk to the table and stand still for 1 second" map directly onto sensor walk
  and still events, with no model call.
* Caution: reviewers scored TSR medium on 54 of our 100 test recordings. The only check run there so far (early
  termination with wrong destination) flagged 9. What they mark as minor must be read from recordings before building the medium side (as with gestures).

**2. Task efficiency.** The repeat taxonomy is a step done twice, so it only covers part of this. Inefficiency is
mostly extra trips. Build a trip log from the sensors: each walk between places, with the items carried on it
(from pick/place events).
* Flag: trips carrying nothing (except the first and last), revisiting a place, and a later pick at a place the
  operator already passed.
* Object grouping comes from the same log: items per trip compared with item size.

**3. Navigation and manipulation.** In the rubric this is not graph order (that belongs to 1). It asks whether the
operator finishes picking or placing before walking. The sensors measure that directly: a walk that starts while a
bend or a hand reach is still going on. Rule plus a frame check on candidates. It is the cheapest new check.

**4. Object handling.**
* Already covered: "where they belong" (the wrong-destination rule inside early termination, 5 of 8 right on
  internal data) and "which object" (wrong tool/object; weak on unseen tasks, precision 0.45, recall 0.31 on
  CaptainCook4D).
* "Move directly": from the item log, an item put down somewhere other than its destination and then moved again.
  This is the correction-loop pattern.
* "No toss or drop": the hand opens above the destination and the item falls. The sensors give hand height and
  speed at release; a frame check confirms.
* "Hands only": frames only (feet, knees). Rare in the data; leave it to a frame question on the release moments.

**5. Scene state.** The off-graph addition check classifies the room. That becomes a scene-scope profile set per
client (household rooms; living area only; field). Out of scope → flag.
* Missing: the "staged / artificially structured" judgement. One frame question at the start: are the task items
  in plausible places, or lined up as if placed for the recording? Use the SOP's own "Starting State / Position"
  text as the reference.
* The rubric says not to fail a recording for setup that the video cannot show. So this should mostly be review,
  not discard.

**Gestural anchoring (already built).** This is the template for the checks above: a free sensor rule, a frame
check only where the rule fires, and a test against reviewer-flagged recordings. On 70 such recordings, all 9 end
discards and 19 of 23 start discards were caught. The task-to-signal time gap does not predict the reviewers'
medium (AUC 0.63 end, 0.43 start). Details in
[2026-10-13_gestural_anchoring_check.md](../benchmarks/2026-10-13_gestural_anchoring_check.md).

**Tested 13–14 Oct: lighting, navigation, efficiency, grouping.** None predicts the reviewers yet; efficiency has
one weak lead (walking much more than recordings of the same task). Walk detection v2 was added to the shared log.
Details in [2026-10-14_task_execution_checks.md](../benchmarks/2026-10-14_task_execution_checks.md).

## What to build, in order

0. Gestural anchoring: done (discard side).
1. Pick/place events per item. They unlock 2, 3, 4 and grouping. v1 is built from the narration (which already
   names the object) and the graph's pick-up and put-down steps, with sensor context at each event. Next: run it
   on all recordings and check the events against frames.
2. Navigation and manipulation (sensor rule) and lighting (pixel statistics). Both are free.
3. TSR severity: criticality tags in the graph, a check of the SOP's "Constraints / Avoid" lines, and the score rule.
4. Trip log → efficiency and grouping.
5. Scene-scope profile and the staged-layout question.

Validate each one as gestural anchoring was validated: search FTS for recordings that reviewers scored medium or
discard on that parameter (`fts_ground_truth search --attrs <parameter>`), download a sample (`s3_fetch`), and
score it against the reviewers. Measure discard and medium separately.
