"""Task graph: schema (v1 and v2), linter, operations, I/O, and the SOP drafters.

The task graph is the reference procedure every check consumes: steps with grounded preconditions
and effects, typed edges, and QC attributes (optional, conditional_on, allowed_substitutes,
permitted_repeats, mandatory_terminal). Version 2 adds what an SOP states beyond that (scenario,
sources, starting state, repeat blocks, acceptance criteria, constraints).
"""
