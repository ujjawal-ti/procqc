# Task execution checks: lighting, navigation, efficiency, grouping (13–14 Oct 2026)

The Snowbird quality rubric (`../../../meta_video_samples/Copy of Snowbird Quality Rubric.pdf`) scores each
recording perfect, medium or discard on a set of execution parameters. This report covers the four that the mapping
doc ([2026-10-13_rubric_task_execution_mapping.md](../architecture/2026-10-13_rubric_task_execution_mapping.md))
expected to be cheap, and the two shared-log parts built for them.

| Parameter | Perfect (short) | Medium | Discard |
|---|---|---|---|
| lighting | hands, objects and room clearly visible | — | — |
| navigation_manipulation | pick or place finished before walking to the destination | occasional minor deviation | repeatedly combines them |
| task_efficiency | no unnecessary trips; picks up objects in the path before walking through | minor unnecessary trip | highly inefficient, repeated unnecessary trips |
| object_grouping | natural groups moved together; medium/large one at a time; small items together | minor grouping inefficiency | repeatedly one at a time when grouping is natural, or unsafe grouping |

## Summary

* **None of the four checks predicts the reviewers yet.** Lighting, navigation and grouping are at chance (AUC
  0.35–0.63, where 0.5 is chance). Efficiency has one weak lead, below.
* **Efficiency lead: walking much more than other recordings of the same task.** At 2.5 times the task's median
  walking distance, we flag 5 recordings and 3 of them are reviewer-flagged (base rate 6 %). At 2 times the median
  number of walks, we flag 7 and 4 are reviewer-flagged. That catches 3–4 of the 10. The cut-offs were chosen on
  this data and are not validated.
* **Frames do not show what reviewers flagged for lighting and navigation.** Flagged recordings look evenly lit, and
  flagged operators pick, turn, carry and place exactly like operators scored perfect.
* **Two shared-log parts now work and are reused by every later check.**
  * Pick/place events from the narration: on the 11-recording pilot, 8 give one pick and one place per item; the other
    3 are grouped carries named as a group.
  * Walk detection v2 (displacement, not speed): recordings longer than 10 s with no walk fell from 14 to 3, and
    narrated walks found by the sensors rose from 74 % to 93 %.
* Cost: $2.10 in model calls (narration of 53 recordings). Every rule and statistic is free.

## Data

* **Set A**: the 100 Meta_Pilot test recordings. Reviewers flagged navigation 4, efficiency 7, grouping 4, lighting 0
  (all medium).
* **Set B**: the 70 downloaded recordings that reviewers flagged at the recording start or end (see the
  [gestural anchoring report](2026-10-13_gestural_anchoring_check.md)). Among them, reviewers flagged lighting 6,
  navigation 9, efficiency 8, grouping 4.
* **Event set (53 recordings)**: pick/place events need a paid narration call, so they were run only on
  * the 11-recording pilot (one per task, $0.40);
  * every local recording flagged on navigation, efficiency, grouping or handling and not already in the pilot (24);
  * 18 recordings scored perfect on all four, round-robin across tasks ($1.70 for the 42).
* **Broken recordings.** 4cd4cac4 and 0c0ac8d3 are 2-second fragments; 7f28a2aa shows an office, not the shoe task
  (its narration came back empty). Reviewers discarded them on several parameters at once. They are left out of the
  efficiency and grouping scores (4 recordings under 10 s or broken).
* Ground truth: the final reviewer step in FTS, fetched read-only (`procqc/audit/fts_ground_truth.py`). Labels are
  used only to score; no model sees them.

## Shared log

### Pick/place events (`procqc/signals/pickplace.py`)

* **Source.** The narration arm (`direct/narrate_judge.py`, 5 fps video, $0.037 per recording) on the clip the
  early-termination check already cut. Its entries are matched to graph steps by text.
* **Rule.** An entry is a pick when it matches a graph step that sets the graph's held predicate true for an object,
  and a place when it matches a step that sets it false. The held predicate is found structurally (each graph names
  it differently). Entries matched to any other step, or marked "no change" by the narration, are walks or handling,
  never picks or places. Each event records the sensor context at its time (walking, bending, still).
* **Pilot (11 recordings).** 8 give one pick and one place per item. In the other 3 the operator carried several items
  together and the narration named the group (a pair of slides, "white plate and ribbed glass"). The event timeline
  is right, but per-item counts by name are not.
* **Not checked:** event times against frames.

### Walk detection v2 (`procqc/signals/walk_v2.py`)

The standard sensor log calls a walk a stretch with head speed above 0.35 m/s for 0.5 s. On Set B, 14 of 67
recordings had no walk at all. Their heads travelled 2–22 m (median 8.6 m, the same as recordings with walks), and
frames show the operators walking between places. They walk slowly: 95th-percentile head speed 0.27–0.38 m/s, against
a median of 0.48 m/s for recordings with walks. Set A had none of these.

v2 calls a walk a moving stretch (head speed above the standard log's still threshold, 0.12 m/s; pauses under 0.3 s
bridged) whose net horizontal displacement is at least 0.5 m (the standard log's place radius). Each walk is trimmed
to where the head leaves its starting spot and reaches its final one (0.06 m = still speed × minimum still time).
No constant was tuned on this data. The standard log and its output are unchanged.

| Check | v1 | v2 |
|---|---|---|
| v1 walks with a path ≥ 0.5 m kept | — | 385 of 389 |
| Set B recordings > 10 s with no walk | 14 | 3 |
| Narrated walks (from the video) found by the sensors, ±1 s | 202 of 274 (74 %) | 256 of 274 (93 %) |
| Sensor walks also narrated, ±1 s | 283 of 316 (90 %) | 261 of 284 (92 %) |
| Walks overlapping a thumbs-up marker (operator standing) | 1 of 302 | 6 of 302 (2 over 0.5 s) |

The 3 recordings still without walks look right in frames: in two the pet bed is moved on the spot, the third is the
office recording. The narration is a second model, not ground truth; there are no hand-labelled walks.

## Results

AUC = probability that a reviewer-flagged recording scores worse than a perfect one (0.5 = chance). All walk-based
numbers use v2 walks.

### Lighting (`procqc/signals/lighting.py`)

Per frame at 1 fps: mean brightness, contrast, share of near-black and of clipped pixels; per recording the median
frame and the worst 10 %.

| Statistic (median / worst 10 %) | AUC, Set B (6 flagged of 70) |
|---|---|
| brightness | 0.54 / 0.63 |
| contrast | 0.51 / 0.28 |
| near-black share | 0.33 / 0.40 |
| clipped share | 0.50 / 0.44 |

Frames from the 6 flagged recordings look evenly lit, with no dark stretch or glare. One (4cd4cac4) is a 2-second
fragment. What reviewers call poor lighting is not brightness or contrast here.

### Navigation and manipulation (`procqc/signals/nav_manip.py`)

| Signal | Recordings (flagged) | AUC |
|---|---|---|
| walk overlapping a bend ≥ 0.3 s (sensors only) | 168 (12) | 0.47 |
| walk overlapping a bend or a grip (sensors only) | 168 (12) | 0.38 |
| picks/places inside a walk (events) | 53 (12) | 0.48 |
| share of picks/places inside a walk (events) | 53 (12) | 0.50 |

Frame review of the 9 flagged recordings that have events (all medium), with 4 frames per event from 1.5 s before to
1.5 s after, and 2 perfect pillow recordings as a reference. Everyone stops or bends at the moment of the pick or
place, then turns toward the destination while still lifting. The flagged and perfect recordings look the same.
Two of the 3 navigation discards are the 2-second fragments; the third is the office recording.

### Task efficiency (`procqc/signals/trips.py`)

A trip is one v2 walk, labelled with what the hands carry at its midpoint (from the events).

| Signal | Recordings (flagged) | AUC |
|---|---|---|
| extra empty trips (beyond one per loaded trip, plus one) | 50 (10) | 0.58 |
| picks at a spot an earlier trip already walked through | 50 (10) | 0.63 |
| walking distance / same-task median (sensors only) | 164 (10) | 0.57 |
| number of walks / same-task median (sensors only) | 164 (10) | 0.65 |

| Cut-off (chosen on this data) | We flag | Reviewer-flagged among them | Reviewer-flagged caught |
|---|---|---|---|
| distance ≥ 1.5 × task median | 31 | 4 | 4 of 10 |
| distance ≥ 2.0 × | 9 | 3 | 3 of 10 |
| distance ≥ 2.5 × | 5 | 3 | 3 of 10 |
| walks ≥ 1.5 × | 22 | 5 | 5 of 10 |
| walks ≥ 2.0 × | 7 | 4 | 4 of 10 |

The reviewer-flagged recordings with the most walking: 7744f17b (coasters, 4.2× the task median), 51feba50
(medium toys, 2.9×), 555190b9 (pillows, 2.5×).

### Object grouping (`procqc/signals/trips.py`)

| Signal | Recordings (flagged) | AUC |
|---|---|---|
| loaded trips per object | 48 (6) | 0.35 |
| objects per loaded trip | 46 (6) | 0.60 |
| share of single-object trips | 46 (6) | 0.40 |

The signals point in opposite directions, so there is nothing consistent. Three of the 6 flagged are shoe
recordings, which suggests reviewers expect a pair of shoes to travel together.

## Where it works and where it doesn't

* **Works:** the shared log. Pick/place events give the right timeline, and walk v2 finds slow walkers without adding
  false walks.
* **Partly:** efficiency through walking compared with peers on the same task. It is free and has a lift over the base
  rate, but only on 10 flagged recordings with cut-offs chosen after seeing them.
* **Doesn't:**
  * lighting from pixel statistics;
  * navigation from walk overlaps, by sensors or events;
  * grouping from carry counts.
* **Why grouping and per-item signals are weak:**
  * Object names collapse: four coasters all called "coaster" count as 1 object.
  * Object size is unknown, and the rubric's grouping rule depends on it (medium/large one at a time, small together).
  * Too few flagged recordings: 6.
* **Reviewer mediums are rare and quiet.** On these parameters 1–6 % of recordings are flagged, and the frames rarely
  show a visible difference. The same was found for the gesture mediums.

## Open

* **Validate the efficiency lead** on recordings it was not tuned on. Search FTS for task_efficiency medium/discard
  (`fts_ground_truth search --attrs task_efficiency`), download a sized and approved sample (`s3_fetch`), and run the
  rule on the sensors only. No model cost.
* **Grouping fixes:** count objects per narration entry rather than by name; add a size class per object from the SOP
  or graph (one text call per task).
* **Walk v2:** look at the 2 walks that overlap a thumbs-up by more than 0.5 s; check in frames that Set A's lower walk
  count (median 6 → 5) is short pauses merging.
* **Pick/place event times** against frames.
* **Switch the gesture boundary score to v2 walks** (it uses the first walk as the task start). Not done; its report
  numbers are on v1 walks.

## Reproduce

```
D=out/internal/meta_pilot; B=$D/boundary_test; M=../meta_video_samples
# walk v2 (free)
python3 -m procqc.signals.walk_v2 ../procqc/out/sensors/meta_pilot_events.jsonl $M/Meta_Pilot_sensors $D/events_walk_v2.jsonl
python3 -m procqc.signals.walk_v2 $B/events_70.jsonl $M/Meta_Pilot_boundary_sensors $B/events_walk_v2.jsonl
# pick/place events: paid narration ($0.037 per recording), then re-derived with v2 walks (free)
python3 -m procqc.signals.pickplace $D/manifest.jsonl ../procqc/out/sensors/meta_pilot_events.jsonl \
    $D/termination_v2_split_all $D/pickplace --only $(cat $D/pilot11.txt $D/pickplace_eval.txt | tr '\n' ' ')
python3 -m procqc.signals.pickplace $B/manifest.jsonl $B/events_70.jsonl $B/termination $B/pickplace \
    --only $(cat $B/pickplace_eval.txt | tr '\n' ' ')
python3 -m procqc.signals.pickplace $D/manifest.jsonl $D/events_walk_v2.jsonl $D/termination_v2_split_all \
    $D/pickplace_walk_v2 --from $D/pickplace
python3 -m procqc.signals.pickplace $B/manifest.jsonl $B/events_walk_v2.jsonl $B/termination \
    $B/pickplace_walk_v2 --from $B/pickplace
# checks (free)
python3 -m procqc.signals.lighting $B/manifest.jsonl $B/lighting --gt $B/fts_gt/ground_truth.csv
python3 -m procqc.signals.nav_manip $D/events_walk_v2.jsonl $B/events_walk_v2.jsonl --out $D/nav_manip_walk_v2 \
    --pickplace $D/pickplace_walk_v2 $B/pickplace_walk_v2 --gt $D/fts_gt/ground_truth.csv $B/fts_gt/ground_truth.csv
python3 -m procqc.signals.trips --set $D/events_walk_v2.jsonl $M/Meta_Pilot_sensors $D/pickplace_walk_v2 $D/manifest.jsonl \
    --set $B/events_walk_v2.jsonl $M/Meta_Pilot_boundary_sensors $B/pickplace_walk_v2 $B/manifest.jsonl \
    --out $D/trips --gt $D/fts_gt/ground_truth.csv $B/fts_gt/ground_truth.csv
```

Run with `PYTHONPATH=.` from the Procedural Errors folder. The efficiency scores without the 4 broken recordings and
the cut-off table were computed from `$D/trips/trips.jsonl`. The frame sheets for the reviews are not saved in the
project.
