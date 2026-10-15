# Catching flaws in auto-generated procedure graphs

The procedure graph is drafted automatically from the SOP, and in live AutoQC no person reviews it. A
drafting flaw then turns into wrong flags on every recording of that task. Three safeguards catch these
flaws without a manual graph review.

## Example flaws (Assembly101 SOP, 9 Oct 2026)

* The SOP line "Repeat steps 1–3 until every part is attached" became a step of its own. Nobody performs
  that line as an action, so the omission check would report it as missing in every recording.
* "If the part is held by a screw, fasten the screw" was marked as required. A toy without screws would
  get an omission flag.

Rewording the SOP fixed both, but live SOPs arrive as they are.

## 1. Structural lint rules (at drafting time, code, no cost)

General rules on the graph's structure, not tied to any task:

* A step that only restates a repeat block's end condition, or refers to other step numbers, is a
  control instruction, not an action. Error.
* A step whose own text sets a condition must be marked optional or conditional. Error.

A graph with an error is re-drafted (the drafter already has a lint-and-repair loop) or held back.

## 2. Go-live gate on the approved recordings (once per task)

Each task's graph comes with 3–5 expert-approved recordings. Before the task goes live, every check runs
on them. They are known to be clean, so any flag on them points to the graph or the check, not to the
demonstrator. A task goes live only when the approved recordings produce no unexplained flags.

The first example above would show up here as "omitted" in every approved recording.

## 3. Monitoring in live use (code, no cost)

For each task and step, track how often the step is flagged and how often reviewers overturn those flags.
A step that is flagged in most recordings, or whose flags are overturned most of the time, points to a
graph flaw rather than demonstrator errors. Then:

* that step's flags go to human review instead of being reported as errors, and
* the task's graph is sent back for re-drafting.

This is the "overturned flags refine the graph" loop of the architecture, as a concrete rule.

## Order of work

1 and 3 cost nothing to run and come first; 2 becomes part of onboarding a task.
