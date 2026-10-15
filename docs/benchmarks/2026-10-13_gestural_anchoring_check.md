# Gestural anchoring: recording start and end signal (12–13 Oct 2026)

The Snowbird quality rubric (`../../../meta_video_samples/Copy of Snowbird Quality Rubric.pdf`) has an attribute
called Gestural Anchoring. It asks whether the recording boundaries are clearly defined. The operator gives two
thumbs up in the camera view immediately before starting the task, and again immediately after finishing it.
The attribute has two parameters, each scored perfect, medium or discard.

| Parameter | Perfect | Medium | Discard |
|---|---|---|---|
| recording_start | Two thumbs up immediately before the task begins, with no unnecessary footage before the signal. | Minor excess footage before the signal, or the signal comes slightly before or after the operator is ready, but the task start stays clear. | The recording begins after the task has started, or the signal is missing or unclear and the boundary cannot be identified. |
| recording_end | The recording captures completion and ends with two thumbs up immediately after it, with no unnecessary footage after the signal. | Minor excess footage after completion or after the signal, but completion and the boundary stay clear. | The recording ends before the task is complete, or the signal is missing or unclear and the boundary cannot be identified. |

The end discard overlaps with our early-termination check: "ends before the task is complete" is that check's
question.

## Summary

* **Discard works.** On 70 recordings that reviewers had flagged, all 9 end discards are flagged by us, 19 of 23
  start discards go to discard or review, and 15 of our 16 discards agree with the reviewers.
* **Medium does not work.** The time between the task and the signal does not predict the reviewers' medium (AUC
  0.63 at the end, 0.43 at the start; 0.5 is chance). A frame review of 16 misses explains only 4 of them.
* **The signal itself is reliable from the sensors.** On 100 recordings that reviewers scored perfect, the sensor
  log alone passed 94 end markers and 85 start markers. A frame check cleared most of the rest; the latest version
  leaves no false "signal missing".
* Cost: the signal and timing checks are free except for one frame call per flagged marker ($0.006). The goal time
  comes from the early-termination check (about $0.01 per recording).

## Data

* **Recordings.** Internal Meta_Pilot headset recordings, 11 household tasks with SOPs from `session.json`
  (verbatim, `out/internal/meta_pilot/sop/`). Video is the left eye (1440×1080, 50 fps) of the stereo original
  (2880×1080). Head and hand sensors run at 72–90 Hz with 26 OpenXR hand joints.
* **Ground truth.** The reviewers' rubric scores in FTS (the headset review workflow), fetched read-only by
  `procqc/audit/fts_ground_truth.py`. The final reviewer step's score is used.
* **Set A: the 100 Meta_Pilot test recordings.** Reviewers scored recording_start and recording_end perfect on all
  100. Only false alarms can be measured on it.
* **Set B: 70 reviewer-flagged recordings.**
  * Search: every recording on the workflow whose final review scored recording_start or recording_end medium or
    discard. That is 672 of 49,190 reviewed recordings (`procqc.audit.fts_ground_truth search`).
  * Workflow-wide counts: start discard 210, medium 184; end discard 55, medium 277.
  * Selection: 82 recordings from the same batch as Set A and our 11 tasks (`procqc.audit.s3_fetch select`, seed 0):
    all 12 end discards, 30 end medium, 25 start discard, 15 start medium. None overlaps with Set A.
  * Downloaded from S3 (`procqc.audit.s3_fetch get`). Every video in a clip folder is the stereo recording, so the
    left eye is cut with ffmpeg. Checked on one Set A recording: same frame count, mean pixel difference 2.7–2.9
    against our local copy.
  * Dropped: 3 recordings with no sensor files on S3, and 9 from a task outside our 11 SOPs ("Return foodware from
    kitchen surfaces to sink"). That leaves 70.
  * Reviewer scores on the 70: end 31 perfect, 29 medium, 9 discard, 1 blank; start 25 perfect, 20 medium, 23
    discard, 2 blank.

## Method

Code: `procqc/signals/gesture_verify.py`. Sensor events come from the standard sensor log
(`Physical AI/procqc`, `procqc.signals.sensors`, unchanged).

**1. Signal from the sensors.** Per hand and per sample, a thumbs-up needs:
* the four fingers curled: fingertip-to-palm distance divided by hand size (wrist to middle-finger base) below
  0.62 for every finger;
* the thumb extended: above 0.95 on the same scale;
* the thumb pointing up: vertical share of the thumb direction above 0.35.

The pose must hold at least 0.25 s after 0.3 s majority smoothing. A gesture within 3 s of the start is the start
marker, and one within 3 s of the end is the end marker. Two hands pass with no model call. One hand, or no
marker, is flagged.

**2. Frame check on flagged markers only.** Six frames go to one Fuelix gemini-3.8-flash call (768 px, reasoning
"low"). The frames span the marker ±0.3 s, or the first 3 s / last 4 s when there is no marker. The model says
what the frames show.

| Answer | v1 decision | v2 decision |
|---|---|---|
| two thumbs up | pass | pass |
| one thumb up | review (the protocol asks for two) | review |
| a deliberate hand signal that is not a clear thumbs-up | not an option | review |
| no thumbs-up (v1) / no deliberate hand signal (v2) | confirmed missing | confirmed missing |
| unclear | review | review |

**3. Timing, with no model call.** The goal time comes from the early-termination check
(`procqc/direct/termination_v2.py`, items rule split). It is the latest placement of any task item, wherever it
was put; whether the place is right is the destination check's question. If no placement time is given, the time
the completion condition was met is used.

| | Discard | Review | Medium | Perfect |
|---|---|---|---|---|
| recording_end | early termination confirmed, or end signal confirmed missing | either of those at review | goal-to-signal gap > 2 s, > 2 s of footage after the signal, or the end signal held > 3 s (added 13 Oct) | otherwise |
| recording_start | start signal confirmed missing | start signal at review, or a bend or grip begins before the signal | > 2 s of footage before the signal, or > 2 s from the signal to the first walk, bend or grip | otherwise |

The 2 s limit is the rubric's own pause limit: "do not pause more than 2 seconds" (Natural Transitions). It was
not tuned on either set.

Two rules added on 13 Oct, after the Set B frame review:
* **Signal hold.** An end signal held longer than 3 s is medium. The headset app appears to stop recording about
  2 s after it sees the end gesture, so a longer hold is footage after the signal. The 3 s limit allows 1 s of
  slack. It comes from our recordings, not from the rubric.
* **Goal time sanity.** A goal time more than 1 s (two frames at 2 fps) after the start of the end signal is
  invalid, because the early-termination check only sees the recording up to the end signal. No gap is measured
  and a note is kept.

## Results on Set A (100 recordings, all perfect)

**Signal.**
* Sensor log: end markers 94 two-handed and 6 one-handed; start markers 85 two-handed, 12 one-handed, 3 missing.
* Every one-handed case failed only the finger-curl limit (0.64–0.85 against 0.62): loosely closed fingers.
* The 3 missing starts are real thumbs-ups. One had thumbs tilted (vertical share 0.30–0.35). Two were cut to
  0.1–0.3 s because the recording began as the gesture ended.
* Frame check v1 on the 21 flagged markers: 19 cleared, 2 confirmed missing (34dd1950, 75670975). Both were false:
  the hands were held out in a deliberate signal with the thumbs angled inward.
* Frame check v2 on those 2: 34dd1950 goes to review. 75670975 passes, but on the same frames v1 had answered
  "none", so that is model variance, not the new answer.
* A looser start search (`procqc/signals/start_marker_v2.py`) finds all 3 missing starts, with 0 fires in 1,115
  mid-recording windows. It is not used: the rubric requires two thumbs up, and the decision was to keep the
  standard sensor log plus the frame check.

**Timing.**

| | perfect | medium | review | discard |
|---|---|---|---|---|
| recording_end, ours | 76 | 23 | 0 | 1 |
| recording_start, ours | 69 | 30 | 1 | 0 |
| reviewers | 100 | 0 | 0 | 0 |

* The end discard is f46e8b0b: the early-termination check took a shoe sole for a task item.
* End gaps: median 1.4 s; 76 at 2 s or less, 20 between 2 and 4 s, 3 over 4 s (4.1, 4.6, 5.5 s).
* Start gaps: 70 at 2 s or less, 25 between 2 and 4 s, 5 over 4 s (largest 6.0 s). Footage before the start
  signal is at most 0.12 s.
* A first version counted only items placed at the destination. It showed 37 s and 17 s gaps on two toy-room
  recordings whose last plush went onto a rack, a placement the user judged acceptable. Fixed: any placement
  counts.

## Results on Set B (70 reviewer-flagged recordings)

Frame check v2 throughout. Cost $1.13 (termination $0.87, frame check $0.26).

**Sensor markers.** Start: 32 two-handed, 7 one-handed, 31 missing. End: 61 two-handed, 5 one-handed, 4 missing.
After the frame check, start: 51 pass, 8 review, 11 confirmed missing; end: 69 pass, 1 confirmed missing.

| recording_end: ours ↓ / reviewers → | perfect | medium | discard |
|---|---|---|---|
| perfect | 23 | 16 | 0 |
| medium | 8 | 12 | 3 |
| review | 0 | 0 | 2 |
| discard | 0 | 1 | 4 |

| recording_start: ours ↓ / reviewers → | perfect | medium | discard |
|---|---|---|---|
| perfect | 14 | 13 | 3 |
| medium | 11 | 7 | 1 |
| review | 0 | 0 | 8 |
| discard | 0 | 0 | 11 |

**Discard.**
* End: all 9 reviewer discards are flagged (4 discard, 2 review, 3 medium). 4 of our 5 discards agree; the fifth
  was scored medium by the reviewers. They come from the early-termination check or a missing signal.
* Start: 19 of 23 reviewer discards go to discard or review. All 11 of our discards agree. The cause is a missing
  start signal.

**Medium.**
* The gap barely separates reviewer medium from perfect: AUC 0.63 at the end, 0.43 at the start.
* End: median goal-to-signal gap 1.8 s for medium, 1.3 s for perfect.
* Footage after the end signal is about 0 s in every recording, because the recording stops at the signal.
* The 2 s rule misses 16 of 29 end mediums and 13 of 20 start mediums. It marks 8 of 31 perfect ends and 11 of 25
  perfect starts as medium.

**Frame review of the 16 end misses** (reviewers medium, ours perfect; 8 frames from before the goal state to the
last frame, `out/internal/meta_pilot/boundary_test/frames_end_medium/`).
* 3 hold the end signal much longer than usual: c3edfcb3 for 13 s while turning around the room, 4d6a6603 for
  about 10 s, 41e9b4ff for 5 s. In 4d6a6603 the frames show the signal from 90 s, but the sensor marker starts at
  96 s because the thumbs pointed forward at first.
* 1 has a small, distant signal low in the frame (b05e4b6d), so "unclear" is plausible.
* 12 look clean: last item placed, hands up within about 1–2 s, a clear two-thumbs-up, recording stops. Nothing at
  the boundary separates them from recordings that reviewers scored perfect.

**Signal hold.** 46 of the 66 end markers on this set last 1.9–2.1 s, which suggests the headset app stops recording
about 2 s after it sees the gesture. A hold longer than 3 s occurs in 5 of 29 reviewer-medium ends and in 0 of 31
perfect ends. That was found on this set, so it is optimistic (and Set A contradicts it; see the re-score below).

**Bug.** One goal time came out after the end signal (4d6a6603, gap −23.9 s). The model gave a placement time beyond
the end of the clip it saw. A goal time later than the end moment should be treated as invalid.

## Re-score with the signal-hold and goal-time rules (13 Oct 2026)

Free: the same sensor events, frame-check answers and early-termination outputs, scored again. Earlier scores are
kept as `boundaries_before_hold.jsonl` in each output folder.

**The signal-hold rule adds as many false alarms on Set A as it catches on Set B.**

| | Set A end (100, all perfect) | Set B end (70) |
|---|---|---|
| medium before → after | 23 → 26 | 23 → 26 |
| new mediums the reviewers also called medium | – | 3 (41e9b4ff 4.8 s, 4d6a6603 3.2 s, c3edfcb3 13.1 s) |
| new mediums the reviewers called perfect | 3 (2ca2a76e 3.1 s, 3e92ec96 3.3 s, 5841c623 3.1 s) | 0 |

* Set B, recording_end against the reviewers: reviewer medium caught 12 → 15 of 29. Reviewer perfect marked medium
  stays 8 of 31. Discard is unchanged.
* Set A: a fourth long hold (cd361950, 3.7 s) was already medium for its gap.
* Holds over 3 s on both sets: 3.1, 3.1, 3.2, 3.3, 3.6, 3.7, 4.2, 4.8 and 13.1 s. The Set A ones that reviewers
  scored perfect are all 3.1–3.7 s. The Set B ones scored medium include 3.2 and 3.6 s. A hold of 3–4 s therefore
  does not separate the reviewers' scores. Above 4 s, all 3 holds (4.2, 4.8, 13.1 s) are reviewer medium, but 3 is
  too few to set a limit on.
* End-signal hold on all 166 markers: 126 last 1.9–2.1 s, 18 last 2.1–3 s, 13 under 1.9 s, 9 over 3 s.
* The goal-time rule applies once: 4d6a6603 (goal time 120.0 s against an end signal at 96.1 s) is no longer read
  as a −23.9 s gap. Its score is medium from the signal hold.
* Recording start is unchanged on both sets.

## Where it works and where it doesn't

**Works or may work.**
* Clear two-handed signals, from the sensors alone.
* Missing signals, through the sensor log plus the frame check (start discard: all 11 of ours agree).
* Recordings that end before the task is done, through the early-termination check (end discard).
* Footage outside the signal, straight from the sensor timestamps; in practice only a long signal hold creates it.

**Doesn't or may not.**
* Reviewer medium, at the start and at the end. Most reviewer mediums show no boundary difference we can see, so
  either reviewers grade something else there or the grade varies between reviewers.
* Borderline hands: thumbs angled, fingers loosely closed, fisheye view. The frame check's answer changed on the
  same frames once.
* The start gap is measured to the first sensor activity, not to the first task action.
* The goal time is read from video at 2 frames per second, about ±0.5 s.
* 3 of 82 downloaded recordings had no sensor files; for those the check cannot run as built.

**How hard the error type is.** Easy for discard: a missing signal or an unfinished task. Medium is hard, because
what reviewers mark is not visible at the boundary in most cases.

**How hard the data is.** Easy with head-mounted sensors. On video alone, every recording would need a frame call.

**Published.** Our research notes cover no dataset or method that scores recording boundary signals.

## Open

* Signal hold: keep 3 s (3 true and 3 false new mediums), raise it to 4 s (no false ones here, but only 3 cases), or
  send long holds to review instead of scoring them medium.
* Treat medium as "for review" rather than predicting it, unless reviewers can say what they mark.
* Run frame check v2 on the 19 Set A markers that v1 cleared (about $0.12).
* For the frame check's variance: two calls on different frame subsets keeping the stricter answer, or more frames
  (`procqc/OPTIMIZATION.md` section 9).
* Optional local model for the signal: the smallest Qwen3 vision model (licence fine). Laya-vision is not used:
  its weights are non-commercial.
* Recordings with no sensor files: decide whether the frame check alone should score them.

## Reproduce

```
# Set A
python3 -m procqc.signals.gesture_verify ../procqc/out/sensors/meta_pilot_events.jsonl ../meta_video_samples/Meta_Pilot \
    out/internal/meta_pilot/boundaries --gestures out/internal/meta_pilot/gesture_verify/gestures.jsonl \
    out/internal/meta_pilot/gesture_verify_v2_recheck/gestures.jsonl \
    --termination out/internal/meta_pilot/termination_v2_split_all --gt out/internal/meta_pilot/fts_gt/ground_truth.csv
# Set B
python3 -m procqc.audit.fts_ground_truth search out/internal/meta_pilot/fts_gt/boundary_search
python3 -m procqc.audit.s3_fetch select out/internal/meta_pilot/fts_gt/boundary_search/boundary_cases.csv \
    out/internal/meta_pilot/sop out/internal/meta_pilot/fts_gt/boundary_search/test_clips.csv --batch BATCH_PREFIX \
    --take recording_end=discard:13 recording_end=medium:30 recording_start=discard:25 recording_start=medium:15
python3 -m procqc.audit.s3_fetch get out/internal/meta_pilot/fts_gt/boundary_search/test_clips.csv \
    ../meta_video_samples/Meta_Pilot_boundary ../meta_video_samples/Meta_Pilot_boundary_sensors
python3 -m procqc.direct.termination_v2 run out/internal/meta_pilot/boundary_test/manifest.jsonl \
    out/internal/meta_pilot/boundary_test/termination --items-rule split
python3 -m procqc.signals.gesture_verify out/internal/meta_pilot/boundary_test/events_70.jsonl \
    ../meta_video_samples/Meta_Pilot_boundary out/internal/meta_pilot/boundary_test/boundaries --verifier v2 \
    --termination out/internal/meta_pilot/boundary_test/termination \
    --gt out/internal/meta_pilot/boundary_test/fts_gt/ground_truth.csv
```

The Set B selection above uses the corrected task matching (Objects and To lines together). The original selection
matched on the To line only and gave 20 cups recordings the dishware task; the manifest took the task from each
recording's own `session.json` instead. The sensor events for Set B were made with the standard sensor log on
`../meta_video_samples/Meta_Pilot_boundary_sensors`, then limited to the 70 recordings (`events_70.jsonl`).
