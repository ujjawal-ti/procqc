# Off-graph addition as its own check (1 Oct 2026)

Code: `procqc/direct/offgraph.py` (candidates + verifier v1), tests `procqc/tests/test_offgraph.py`.
Runs: `out/offgraph_check/{synth_tune, cc4d_dev, cc4d_tomato}`, probe `out/offgraph_check/role_probe.json`.

## Method

An off-graph addition is a self-contained action that is no step of the procedure and serves none
(EgoPER "Step Addition": unnecessary extra steps not in the task graph). Supporting work is not an
addition: fetching, opening, washing or measuring out what a step uses, putting a step's tool away,
discarding its waste, adjusting the current object in place, reading the instructions.

* **Narration and matching**: the cached ones shared with the omission and misordering checks (match v1).
* **Candidates, one text call**: every entry with no matched step gets a role (prepare, tidy, adjust,
  instructions, transition, unrelated); the object is judged first ("is it used by any step?"). Entries
  marked `unrelated`, and entries the narrator marked `scene_change`, are candidates; consecutive ones
  (gap at most 2 s) merge.
* **Verifier v1, one video call**, two clips: the candidate span (padded 2 s, 4 to 60 s) and an 8 s
  reference of the main task just before it. Questions: same setting? does the action perform, prepare,
  tidy after or adjust a listed step? verdict. Addition, and (serves no step or another setting), with
  confidence at least 0.6 confirms; serves a step rejects; otherwise review.
* Scoring: no step id, so a detection matches a labelled addition by time overlap (1 s tolerance).

## Data

* Synthetic Lightwheel set: 49 videos with a 1.5-6 s action from another task's recording spliced in,
  50 clean videos. Split by source recording: tuning 20 + 20, held-out 29 + 30
  (`manifest_offgraph.jsonl`, `manifest_offgraph_val.jsonl`).
* CaptainCook4D, 36 recordings: **no addition labels exist in this dataset** (its categories are
  missing step, order, measurement, technique, preparation, timing, temperature). Used for false alarms
  only; a flag there is not necessarily wrong.

## Results

| set | with addition found | clean flagged | events TP / FP / FN | cost | latency p50 |
|---|---|---|---|---|---|
| synthetic tuning, no verifier | 20 / 20 | 0 / 20 | 20 / 0 / 0 | $2.22 (narration not cached) | 46 s |
| synthetic tuning, verifier v1 | 20 / 20 | 0 / 20 | 20 / 0 / 0 | (included) | |
| CC4D development, both | n/a | 0 / 21 | 0 candidates | $0.32 | 17 s |
| CC4D Tomato Chutney (held-out), both | n/a | 0 / 15 | 0 candidates | $0.19 | 14 s |

**What the synthetic result does not show.** All 20 detections came from the narrator's
`scene_change` flag; the role classifier never fired on the synthetic set. The spliced actions are
footage from another room, so this set tests only the easy case. A real addition happens in the same
room, and that path (unmatched entry, role `unrelated`) is untested on video.

**Text-only probe of the same-room path** ($~0.5). One off-procedure entry inserted into each of the 36
cached real narrations; only the role call re-run:

| inserted entry | classified unrelated |
|---|---|
| a step of another recipe, same kitchen (dice tomato in the egg sandwich, crack an egg in the chutney, peel garlic in the wraps) | 12 / 12 |
| check messages on a smartphone | 12 / 12 |
| water a potted plant | 12 / 12 |

Two recordings also had one original entry newly marked unrelated (15_30 "press microwave buttons"
during Tomato Chutney, which uses no microwave; 1_36 "pull serrated knife"). These would go to the video
verifier. The first may be a real addition. The probe assumes the narration describes the action; it
does not test whether the narrator writes it down.

**Known limit: coarse narration of long recordings.** The video call samples at most 900 frames, so a
25-41 min recording gets 0.36-0.6 fps and 20-30 entries (15_2: 20 entries in 25 min; 15_5: 29 in 41 min).
A 3-5 s addition there can be merged into a neighbouring entry or skipped.

## Open

* A same-room test on video: splice a step from another recipe recorded in the same kitchen into
  CaptainCook4D recordings (person and kitchen ids are in the metadata; e.g. 1_10 and 28_10, 1_37 and
  28_45, 1_34 and 28_2 share both), then re-narrate.
* Real addition labels: Assembly101 "unnecessary" detach mistakes (377 in the public CSVs; videos are
  gated on Hugging Face), EgoPER Step Addition (access by e-mail request to the authors).
* The synthetic held-out half (59 videos, ~$3.3) is not run: it exercises the same scene-change path
  as the tuning half.
