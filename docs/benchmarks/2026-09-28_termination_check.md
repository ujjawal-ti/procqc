# Early termination as its own check (28 Sep 2026)

First module of the hybrid design: each error kind gets the approach that suits it, instead of all
seven kinds sharing one narration and one step matching. Code: `procqc/direct/termination.py`.

## Method

One call per episode, no full-video narration, no step matching.

* Input: the final moments of the video, cut into a clip (last 10 % of the video, at least 20 s and
  at most 60 s) and sent as native video at 5 frames per second (Google AI Studio). With the
  clip: the required procedure steps numbered by position in the order they are performed (a step
  done several times appears at each position), the mandatory final step with its expected result,
  and the goal.
* The model answers two questions: which position is the last one performed in the clip (read
  from the run of the last two or three actions, because one action text can occur at several
  positions), and whether the final step's result is present, absent or unclear at the end.
* Decision in code: last position = final step → no finding (even if its result is too small to
  see). Last position earlier → early termination, confirmed when the result is absent, review when
  it is unclear or looks present. No procedure step in the clip → decided by the result.

## Test sets

* Tuning (used while developing): 10 synthetic terminations (3 from the smoke set + 7 from other
  source videos), 10 synthetic negatives (5 clean, 5 omission variants, which keep the ending), and
  the 10 CaptainCook4D recordings (no real terminations; 4 clean, 6 with other errors).
* Held-out validation (run once, after development): 10 terminations and 10 negatives (5 clean,
  3 omission, 2 repeat) from source videos not used for tuning.

## Results

| version | synthetic tuning (TP / FN, FP of 10 neg.) | CC4D false alarms of 10 | cost / episode |
|---|---|---|---|
| 1. 10 end frames, final-step result only | 5 / 5, 0 | 3 (2 with a reference recording) | $0.013 |
| 2. + last step from the recent actions (by id) | 6 / 4, 1 | 1 (2 with reference) | $0.018 |
| 3. + positions in the demonstrated sequence | 9 / 1, 1 | 3 | $0.018 |
| **4. native video clip at 5 fps (final)** | **9 / 1, 0** | **0 confirmed, 1 to review** | **$0.010** |
| **4. held-out validation** | **10 / 0, 0** | | **$0.009** |

Final version: 19 of 20 synthetic terminations found, 0 of 20 synthetic negatives and 0 of 10
CaptainCook4D recordings falsely confirmed; one CaptainCook4D recording (28_2) sent to review because
the toothpicks are too small to see. Latency p50 8–20 s per episode, one call. Development cost of
all four versions: about $2.50.

Previous approaches on the 3 smoke-set terminations: per-kind video calls 3 found / 2 false alarms;
narrate → judge 2 found / 1 false alarm (the terminal step matched to a smoothing motion); after fix
round 1, 1 found.

## What each change fixed (verified on frames)

* Version 1 missed four terminations whose final step leaves no distinctive state ("place the
  remote on the table", "close the stapler"): the object was already in that state earlier.
  Reading the last actions instead of only the end state fixed b259cece_term1 (last step = fold the
  cover, the final flip never happened).
* Version 2 still failed where step texts repeat: identical texts share one graph node, so "the last
  step was *place the remote*" could not say which occurrence. The synthetic graphs now record the
  demonstrated sequence (`metadata.canonical_sequence`, ids unchanged) and the model answers with a
  position.
* Versions 1–3 sampled frames 4–6 s apart. 1_7 (clean): replacing the top of the muffin takes 5 s
  (588–593 s) and only one frame landed on it, so the model said "absent" at 0.95. 14a715a9_omit07:
  placing the staple pin takes 0.7 s, between two frames. The 5 fps clip fixed both, and was cheaper.
* A reference recording of the same recipe (final frames of another clean recording) did not help:
  one fewer false alarm on one recording, one more on another.

## Remaining limits

* bb83fa03_term8 (missed): the video stops after "press the remote button, place the remote on the
  table", which is also how the procedure ends (positions 30–31); the ending alone cannot tell the
  two apart. The state of the batteries would, but the synthetic graph has no end state.
* No real early terminations yet: CaptainCook4D has none, so real data only tested false alarms.
  Synthetic terminations are clean cuts; a real one (the person stops and puts the tools down)
  may be subtler. Real positives are needed before deployment.
* Relies on the procedure listing its steps in performed order; for a DAG the topological order is
  used, which is fine for the final step but not a performed sequence.
