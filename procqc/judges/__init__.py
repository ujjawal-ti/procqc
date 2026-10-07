"""Per-kind checks. Each module has a KIND and a `check(ep)` that returns {"kind", "candidates", ...}.

  termination   early termination: a clip of the final moments against the final step (one video call)
  omission      a required step never performed while a step that needs it is (code), video verifier
  misordering   a step performed before its prerequisite (code), video verifier
  offgraph      an action that is no step and serves none (text roles), video verifier
  repeat        a step performed more often than allowed (code), video verifier
  wrongtool     another item than the step specifies (frame and crop calls, closed question)

All but termination read the shared narration (`narration.narrated_sequence`, through `Episode`).
"""
from procqc.judges import misordering, offgraph, omission, repeat, termination, wrongtool

CHECKS = {
    "termination": termination,
    "omission": omission,
    "misordering": misordering,
    "offgraph": offgraph,
    "repeat": repeat,
    "wrongtool": wrongtool,
}
