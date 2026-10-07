"""procqc: procedural-error quality control for recorded demonstrations of a written procedure.

A task graph (drafted from the SOP) is the reference. Per-kind checks compare a recording with it:
early termination, omission, misordering, off-graph addition, redundant repetition, and wrong tool /
object / ingredient. Every check returns candidates with a status (confirmed, needs_review, rejected);
`procqc.judges.base.route` turns them into flags and a human review list.
"""
__version__ = "0.1.0"
