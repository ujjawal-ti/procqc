"""Stakeholder decision page: which procedural-error taxonomy kinds are ready to deploy.

Per kind: status and recommended deployment mode, counts per test set (caught / sent to review /
false alarms / missed, with 95 % intervals), passing and failing scenarios with frames and a plain
explanation, why the kind is hard, and what would fix it. All counts are computed from the stored
verdicts and labels; the scenario explanations are written by hand from those same verdicts.

Run from the repository root:
  uv run python docs/architecture/build_taxonomy_readiness.py --out docs/architecture/taxonomy_readiness.html
"""
from __future__ import annotations

import argparse
import base64
import glob
import html
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from procqc.audit import metrics as M  # noqa: E402
from procqc.audit.labels import adjudicate_labels, load_labels  # noqa: E402
from procqc.direct.arm import _annotated_windows, load_annotated_segments  # noqa: E402
from procqc.graph.io import load_graph  # noqa: E402
from procqc.signals.frames import VideoReader, to_jpeg_bytes  # noqa: E402
from procqc.verify.reconcile import Finding  # noqa: E402

DATASETS = {
    "SYN": {"name": "Synthetic Lightwheel smoke set", "short": "Synthetic",
            "run": "out/synth_lightwheel/narrate_smoke", "labels": "out/synth_lightwheel/labels.jsonl",
            "version": "current pipeline (narrate the video, judge each error kind against the task graph, "
                       "adjudicator with frames from annotator timestamps)",
            "about": "15 re-cut Lightwheel recordings, 3 per injected kind, no clean recordings. Errors were created by "
                     "cutting, duplicating, swapping or splicing clips of real recordings."},
    "CC": {"name": "CaptainCook4D real recordings", "short": "Real (CaptainCook4D)",
           "run": "out/opensource/captaincook4d/narrate_annframes", "labels": "out/opensource/captaincook4d/labels.jsonl",
           "version": "current pipeline (narrate the video, judge each error kind against the recipe graph, "
                      "adjudicator with frames from annotator timestamps)",
           "about": "10 cooking recordings (5.7 to 18.5 min) with real, human-annotated errors, 2 recipes with "
                    "published step-dependency graphs, 4 recordings labelled clean."},
}
PREVIOUS = {"run": "out/synth_lightwheel/direct_kinds_smoke", "labels": "out/synth_lightwheel/labels.jsonl",
            "label": "Previous pipeline version (one video call per error kind) on the same synthetic episodes"}
KINDS = ["early_termination", "addition_offgraph", "omission", "addition_repeat", "misordering",
         "wrong_tool_object", "parameter_deviation"]
TITLE = {"early_termination": "Early termination", "addition_offgraph": "Off-procedure addition",
         "omission": "Omission", "addition_repeat": "Redundant repetition", "misordering": "Misordering (wrong order)",
         "wrong_tool_object": "Wrong tool / object / ingredient", "parameter_deviation": "Step parameter deviation"}

STATUS = {
    "early_termination": ("Ready for assisted QC", "go",
                          "Flag automatically; a reviewer confirms before any action. Watch brief final actions."),
    "addition_offgraph": ("Ready for assisted QC", "go",
                          "Flag automatically; a reviewer confirms. Actions that resemble a listed step can slip through."),
    "omission": ("Assisted QC, known blind spot", "caution",
                 "Flag automatically; a reviewer confirms. Treat omissions of look-alike repeated steps (e.g. one of three microwave steps) as unreliable until the identity convention is fixed."),
    "addition_repeat": ("Not ready, narration gap", "stop",
                        "Keep off. The current narration merges a repeated step into one entry, so the judge never sees the repeat. Fixable in the narration rules; re-test after."),
    "misordering": ("Not ready", "stop", "Keep off in production; keep measuring."),
    "wrong_tool_object": ("Not ready, gap is fixable", "stop",
                          "Keep off; the detector sees several of these events but files them under another kind. Fix the definitions, then re-test."),
    "parameter_deviation": ("Not ready", "stop",
                            "Keep off except for counts that are clearly visible (number of eggs, scoops); keep measuring."),
}

ABOUT = {
    "early_termination": ("The procedure is not carried through to its mandatory final step, so the goal state is never reached.",
                          "One judge reads the narration and checks whether the final step was performed and the goal state holds at the end. It does not care how the video file ends."),
    "addition_offgraph": ("An action that belongs to no step of the procedure and serves none (another activity, an unrelated object).",
                          "The judge looks at narrated actions that match no step and asks whether they prepare, support or tidy up after any step. Only actions that serve no step are reported."),
    "omission": ("A required step is never performed although the procedure continued past it.",
                 "The judge checks, step by step, whether the narration performs it; if not, whether a step that needs it was performed anyway."),
    "addition_repeat": ("A step allowed once is performed again after it was already complete, with no mistake in between.",
                        "The judge compares repeated occurrences of a step and asks whether the first one had already achieved its result."),
    "misordering": ("A step is performed before a step it requires, and the required step is done later.",
                    "The judge walks the narration in time order against the dependency graph (unrelated branches may be done in any order)."),
    "wrong_tool_object": ("A step is performed with a different tool, object or ingredient than specified.",
                          "The judge compares the objects the narration names for each step with the objects the step specifies."),
    "parameter_deviation": ("The right step with the wrong quantity, duration, setting or technique.",
                            "The judge compares quantities, durations and settings the narration reports with those the step text specifies."),
}

WHY = {
    "early_termination": ["The evidence is the end state, which is usually clear: the last unit of work visibly never happens.",
                          "It relies on how the narration describes the last seconds. In one synthetic recording the narration reported the final step as done (it read a pressing motion as 'reposition the book'), so the judge correctly found no termination and reported a skipped step instead.",
                          "Failure mode seen: a very short final action (a one-second 'stand up') in the last seconds of the video is missed, and a termination is reported."],
    "addition_offgraph": ["Spliced footage from another activity is obvious to the model (different room, different objects), and it is reported with the right time window.",
                          "An inserted action that resembles a listed step (a 'sit down' clip in a task that has sitting in it) is matched to that step and not reported.",
                          "On real recordings, ordinary preparation that the procedure does not spell out (fetching, washing, halving) produced 10 false alarms until the definition said that anything serving a step is not an addition; now none."],
    "omission": ["Works when a step's result never appears and later steps that need it are done anyway (mayonnaise never reaches the bowl, avocado never sliced).",
                 "Fails on look-alike repeated steps: the recipe has three 'microwave the ramekin' steps. Which step an action counts as depends on a convention (by position in the sequence, as the annotators use, or by content, as the model does). The prompts do not state one yet.",
                 "Synthetic omissions are a weak test: cutting a clip out leaves the step's effect visible afterwards, so there is often nothing in the video to detect; when the model does react, it blames a neighbouring step."],
    "addition_repeat": ["The narration rules tell the narrator to merge exact repeats into one entry with a count. That rule was meant for wipe strokes and stirring passes, but a duplicated step is exactly such a repeat, so it disappears before the judge sees it.",
                        "The previous version, which asked the video model directly about repeats, found 2 of 3, both only at human-review level.",
                        "Beyond that, the line between a redundant repeat and a correction depends on whether the first attempt had failed, which is an outcome judgement."],
    "misordering": ["The narrator assigns step ids with the procedure in view and tends to follow the written order, so swapped steps can come out in the expected order and the judge sees nothing wrong.",
                    "It inherits every step-identity error: if one action is assigned to the wrong look-alike step, an order violation appears (or disappears).",
                    "Wrong order inside one assembly (which layer goes first) is only implicit in the step list; synthetic swaps are physically impossible for state-changing steps."],
    "wrong_tool_object": ["The detector does see several of these events, but the definitions of 'wrong tool' and 'wrong technique' overlap: tearing a muffin by hand instead of cutting it with a knife was filed as a parameter (technique) deviation.",
                          "Near-synonym objects pass as close enough: a bowl used instead of a ramekin was even named in the narration, but nothing in the procedure says a bowl is not acceptable.",
                          "Some errors concern tools the step text never names (stirring with a knife, chopping without a board); a wrong tool can only be judged against a specified one."],
    "parameter_deviation": ["Of the 19 labelled deviations, most are technique judgements ('stirred too rapidly', 'cracked the egg inappropriately') with no stated threshold, or small quantities (a teaspoon versus a tablespoon) that are hard to see from a head camera at 360p.",
                            "Timing errors need the microwave display or the door-closed time, which the narration does not measure reliably.",
                            "What works: counts that are plainly visible (two eggs instead of one, two scoops instead of one) and clear durations."],
}

FIX = {
    "early_termination": "Sample the final seconds densely; treat body movements (stand up, sit down) as weak final steps; ask the narrator to describe the last seconds explicitly.",
    "addition_offgraph": "Keep the service-action rule; report 'real but unlisted' actions to the procedure owner as possible missing steps; flag narrated actions whose scene differs from the rest of the video.",
    "omission": "List look-alike steps and what distinguishes them in the graph context; let the narrator give all candidate steps for an ambiguous action; state the identity convention (needs a decision); one short text call assigns identities before the judges.",
    "addition_repeat": "Change the narration rule: a whole step performed again is always a separate entry (only strokes within one action are merged). Show the adjudicator both occurrences (done). Re-test on real repeats.",
    "misordering": "Narrate with the objects list but without the step order, and match steps in a separate text pass, so the narration cannot follow the script; plus the identity fix above.",
    "wrong_tool_object": "Define the boundary with parameter deviation (tool or object identity takes precedence); add excluded substitutes to objects (a bowl is not a ramekin); name the tools a step requires when the client's procedure does.",
    "parameter_deviation": "Split into measurable parameters (counts, visible durations, settings shown on a display) and subjective technique; deploy only the measurable part first; technique needs client-defined thresholds.",
}

# Curated scenarios: (dataset, episode_id, kind, step, outcome, what happened, why)
# outcome: caught | caught_review | missed | false_alarm | false_alarm_review | other_kind
SCEN = {
    "early_termination": [
        ("SYN", "659d6b53_term1", "early_termination", None, "caught",
         "The recording was cut before the last unit of work (put the box down, pick up the empty tissue bag and dispose of it). Reported: the procedure ends after pulling a tissue, with the final steps never performed.",
         "The final step visibly never happens; the end state contradicts the goal."),
        ("SYN", "30023601_term1", "early_termination", None, "caught",
         "Cut before the doll is picked up and placed on the shelf; reported with the doll still on the table.", ""),
        ("SYN", "b259cece_term1", "early_termination", None, "missed",
         "Cut before 'flip the book' and 'reposition the book'. The narration reported the final 'reposition' as done (it read a pressing motion that way), so the judge found no termination and reported the flip as skipped.",
         "Termination depends on how the narration describes the last seconds."),
        ("SYN", "eb7d161e_ins01", "early_termination", None, "false_alarm",
         "The person does stand up (the procedure's final step, about one second) in the last seconds. Reported that the video ends while seated.",
         "A very short final action at the very end is easy to miss at the sampling rate used."),
    ],
    "addition_offgraph": [
        ("SYN", "e04d3ead_ins01", "addition_offgraph", None, "caught",
         "A clip from another activity (paperwork at an office cubicle) was spliced into a tabletop task. Reported with the right time window (10.4 to 13.4 s).", ""),
        ("SYN", "b7128398_ins14", "addition_offgraph", None, "caught",
         "A clip of someone working at a computer desk spliced in; reported at 67.6 to 70.3 s.", ""),
        ("SYN", "eb7d161e_ins01", "addition_offgraph", None, "missed",
         "The inserted clip was a 'sit down' taken from another recording. The narration matched it to a listed step, so nothing was reported.",
         "An inserted action that resembles a listed step slips through."),
    ],
    "omission": [
        ("CC", "cc4d_28_25", "omission", "cc03_1_4_cup_mayonnaise_to_the", "caught",
         "Mayonnaise was measured into a cup and left on the cutting board; everything else was mixed and assembled without it.",
         "The step's result never appears and later steps that need it are performed: the clearest omission pattern."),
        ("CC", "cc4d_28_26", "omission", "cc17_cut_avocado_into_thin_slic", "caught",
         "The avocado was halved and pitted but never sliced; slices were never placed and the tuna never went on the leaves; the wraps were rolled empty. All three omissions caught.", ""),
        ("CC", "cc4d_1_34", "omission", "cc03_coat_a_6_oz_ramekin_cup_wi", "caught",
         "The egg was cracked into a ramekin that was never sprayed. Caught.", ""),
        ("CC", "cc4d_1_10", "omission", "cc04_microwave_the_ramekin_cup", "missed",
         "Labelled: the first of three microwave steps was skipped. The person beat the raw egg, then microwaved it twice before the toppings. The model counted the first cycle as the first microwave step and reported the beating as a misordered stir instead.",
         "Look-alike steps. Both readings fit the footage; which is right depends on an identity convention the prompts do not state yet."),
        ("SYN", "d0646d89_omit12", "omission", "g19_insert_the_scissors_into_th", "missed",
         "Synthetic cut: 'insert the scissors into the cover' was removed. The model did react, but blamed two neighbouring steps ('reposition the cover', 'close the cover'), which count as false alarms.",
         "When a cut leaves the scene inconsistent, the model notices but misplaces which step is missing."),
        ("SYN", "52864eed_omit04", "omission", "g04_place_the_red_stamp_pad_on_t", "missed",
         "Synthetic cut: the unit 'place the stamp pad and its lid on the table' was removed, but the pad is on the table in every later frame.",
         "A limitation of the synthetic test: re-cutting leaves the step's effect visible, so the video shows no missing step."),
    ],
    "addition_repeat": [
        ("SYN", "1a08eacf_rep03", "addition_repeat", "g03_insert_the_nozzle_into_the_h", "missed",
         "The nozzle-insertion clip was duplicated. The narration lists the insertion once; the repeat judge reports every step performed exactly once. (The previous version found this one, at review level.)",
         "The narration merges an exact repeat into one entry, so the judge never sees it."),
        ("SYN", "ade37404_rep04", "addition_repeat", "g04_coil_the_wire_around_the_hai", "missed",
         "A 26-second cord-coiling clip was duplicated; the narration describes one coiling. (Also found by the previous version, at review level.)", ""),
        ("SYN", "e2db3119_rep13", "addition_repeat", "g13_place_the_teacup_on_the_clot", "missed",
         "A 1.2-second placement was duplicated; it reads as one continuous motion.", "Short repeats are nearly invisible at the sampling rate."),
    ],
    "misordering": [
        ("SYN", "b7128398_swap15", "misordering", "g24_rearrange_the_plastic_bag", "caught",
         "Two units were swapped so that the plastic bag is handled before the makeup case is closed. Reported: the bag was rearranged before its prerequisite 'close the makeup case'.", ""),
        ("SYN", "1337afbe_swap05", "misordering", "g11_place_the_stapler_on_the_tab", "missed",
         "'Place the stapler on the table' was moved before 'staple the papers'. The narration labelled the steps in the written order, so the judge saw no inversion. (The previous version caught this one.)",
         "The narrator sees the step list and tends to follow it."),
        ("CC", "cc4d_1_32", "misordering", "cc02_place_the_egg_from_the_cup", "missed",
         "Labelled order error: the lettuce was removed, the egg placed, then the lettuce put on top of the egg.",
         "The wrong order is inside one assembly (which layer first), which the step list describes only implicitly."),
        ("CC", "cc4d_1_10", "misordering", "cc11_stir_the_ramekin_cup", "false_alarm",
         "Reported 'stirred before microwaving'. Physically true, but the annotators treat the beating as the stir step and the first microwave step as skipped.",
         "Same look-alike identity problem as omission; misordering inherits every step-identity error."),
    ],
    "wrong_tool_object": [
        ("CC", "cc4d_1_32", "parameter_deviation", "cc12_cut_the_english_muffin_int", "other_kind",
         "Labelled: the English muffin was split by hand instead of cut with a knife. The pipeline saw it and reported it, but as a parameter (technique) deviation.",
         "Scores as a missed wrong-tool error and a false parameter alarm. The two definitions overlap; fixable."),
        ("CC", "cc4d_1_32", "wrong_tool_object", "cc01_pour_1_egg_into_the_rameki", "missed",
         "Labelled: a bowl was used instead of the ramekin. The narration even calls it a 'ceramic bowl', but the judge did not treat it as a different object.",
         "Near-synonym objects: nothing in the procedure says a bowl is not acceptable."),
        ("CC", "cc4d_1_34", "wrong_tool_object", "cc11_stir_the_ramekin_cup", "missed",
         "Labelled: stirred with a knife.", "The recipe never names the stirring tool, so there is nothing to compare against."),
    ],
    "parameter_deviation": [
        ("CC", "cc4d_1_32", "parameter_deviation", "cc01_pour_1_egg_into_the_rameki", "caught",
         "Two eggs were cracked where the recipe says one. Caught.", "Counts that are plainly visible work."),
        ("CC", "cc4d_1_32", "parameter_deviation", "cc06_top_cup_with_1_tablespoon", "caught",
         "Two tablespoons of salsa instead of one; two scoops seen. Caught.", ""),
        ("CC", "cc4d_1_28", "parameter_deviation", "cc06_top_cup_with_1_tablespoon", "missed",
         "Labelled: one teaspoon of salsa instead of one tablespoon.", "Spoon size is hard to tell from above at 360p."),
        ("CC", "cc4d_1_32", "parameter_deviation", "cc11_stir_the_ramekin_cup", "missed",
         "Labelled: stirred too rapidly.", "A subjective technique judgement with no threshold in the procedure."),
    ],
}
PREV_C: dict = {}
OUTCOME = {"caught": ("Caught", "go"), "caught_review": ("Caught, sent to human review", "caution"),
           "missed": ("Missed", "stop"), "false_alarm": ("False alarm", "stop"),
           "false_alarm_review": ("False alarm, sent to review", "caution"),
           "other_kind": ("Detected, but filed under another kind", "caution")}


def b64(fr, edge=260, q=62):
    return base64.b64encode(to_jpeg_bytes(fr, long_edge=edge, quality=q)).decode("ascii")


def load(ds):
    d = DATASETS[ds]
    gold = adjudicate_labels(load_labels(str(ROOT / d["labels"])))
    V = {json.load(open(p))["episode_id"]: json.load(open(p)) for p in glob.glob(str(ROOT / d["run"] / "verdicts" / "*.json"))}
    return gold, V


def classify(gold, V):
    """Per finding: TP / FP (by final status), per gold finding: FN. Same rules as the scoring code."""
    rows = []
    for eid, v in V.items():
        gl = gold[eid]
        used = set()
        segs = v.get("segments", [])
        term_seen = False
        for f in v["findings"]:
            st = f.get("final_status", f.get("status"))
            if st not in ("confirmed", "needs_human"):
                continue
            raw = (f.get("adjudication") or {}).get("final_kind") or f["kind"]
            if raw in ("none", "None"):
                raw = f["kind"]
            kind = M.KIND_ALIASES.get(raw, raw)
            step = (f.get("missing") or [f.get("step")])[0] if kind == "early_termination" else f.get("step")
            if kind == "early_termination":
                if term_seen:
                    continue
                term_seen = True
            p = {"kind": kind, "step": step, "start": f.get("segment_start"), "confidence": f.get("confidence", 0)}
            hit = None
            for j, gf in enumerate(gl.findings):
                if j not in used and M._match(p, gf, segs):
                    hit = j
                    used.add(j)
                    break
            rows.append({"t": "TP" if hit is not None else "FP", "status": st, "kind": kind, "eid": eid})
        for j, gf in enumerate(gl.findings):
            if j not in used:
                rows.append({"t": "FN", "status": "-", "kind": gf.kind, "eid": eid})
    return rows


def counts(rows, gold, kind, episodes):
    rs = [r for r in rows if r["kind"] == kind]
    n_gold = sum(1 for eid in episodes for f in gold[eid].findings if f.kind == kind)
    c = {"gold": n_gold,
         "tp": sum(1 for r in rs if r["t"] == "TP" and r["status"] == "confirmed"),
         "tp_rev": sum(1 for r in rs if r["t"] == "TP" and r["status"] == "needs_human"),
         "fp": sum(1 for r in rs if r["t"] == "FP" and r["status"] == "confirmed"),
         "fp_rev": sum(1 for r in rs if r["t"] == "FP" and r["status"] == "needs_human")}
    c["fn"] = n_gold - c["tp"] - c["tp_rev"]
    return c


def frames_for(ds, eid, kind, step, outcome, V, gold, n=3):
    v = V[eid]
    dur = v["localization"]["duration"]
    window = None
    if outcome != "missed":
        for f in v["findings"]:
            k = (f.get("adjudication") or {}).get("final_kind") or f["kind"]
            if k in ("none", "None"):
                k = f["kind"]
            kk = M.KIND_ALIASES.get(k, k)
            if (kk == kind or f["kind"] == kind) and (step is None or f.get("step") == step) and \
                    f.get("final_status") in ("confirmed", "needs_human"):
                try:
                    a, b = f["evidence"][0].rstrip("s").split("-")
                    window = (float(a), float(b))
                except Exception:  # noqa: BLE001
                    s = f.get("segment_start") or 0.0
                    window = (s, s + 2)
                break
    if window is None:
        gf = next((g for g in gold[eid].findings if g.kind == kind and (step is None or g.step == step)), None)
        if gf is not None and gf.start is not None:
            window = (gf.start, gf.end if gf.end and gf.end > gf.start else gf.start + 2.0)
        elif ds == "CC":
            ann = load_annotated_segments(str(ROOT / DATASETS["CC"]["labels"]))
            g = load_graph(v["manifest"]["graph"])
            W = _annotated_windows(g, Finding(kind, "confirmed", step, "", 0.9), ann[eid], dur)
            if W:
                window = (W[0][1], W[0][2])
    if window is None:
        window = (max(0, dur - 6), dur)
    a, b = max(0.0, window[0] - 1.0), min(dur - 0.05, max(window[1], window[0] + 1.0) + 1.0)
    if kind == "early_termination":
        a, b = max(0.0, dur - 6.0), dur - 0.1
    out = []
    with VideoReader(v["video"]) as video:
        for t in np.linspace(a, b, n):
            fr = video.frame_at(float(t))
            if fr is not None:
                out.append((round(float(t), 1), b64(fr)))
    return out


def pct(k, n):
    if not n:
        return "–"
    r, lo, hi = M.wilson(k, n)
    return f"{100 * r:.0f} % <span class='ci'>({100 * lo:.0f}–{100 * hi:.0f})</span>"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs/architecture/taxonomy_readiness.html"))
    a = ap.parse_args()
    data = {ds: load(ds) for ds in DATASETS}
    rows = {ds: classify(*data[ds]) for ds in DATASETS}
    C = {ds: {k: counts(rows[ds], data[ds][0], k, data[ds][1].keys()) for k in KINDS} for ds in DATASETS}
    global PREV_C
    pg = adjudicate_labels(load_labels(str(ROOT / PREVIOUS["labels"])))
    pv = {json.load(open(p))["episode_id"]: json.load(open(p)) for p in glob.glob(str(ROOT / PREVIOUS["run"] / "verdicts" / "*.json"))}
    prow = classify(pg, pv)
    PREV_C = {k: counts(prow, pg, k, pv.keys()) for k in KINDS}
    clean = {}
    for ds, (gold, V) in data.items():
        cl = [eid for eid in V if gold[eid].clean]
        flagged = [eid for eid in cl if any(f.get("final_status") == "confirmed" for f in V[eid]["findings"])]
        clean[ds] = (len(flagged), len(cl))

    esc = html.escape
    parts = []
    # --- summary table ---
    summ = ["<table class='summary'><tr><th>Error kind</th><th>Status</th><th>Test set</th><th>Labelled</th>"
            "<th>Caught</th><th>Sent to review</th><th>False alarms</th><th>Missed</th><th>Precision (95 % CI)</th>"
            "<th>Recall (95 % CI)</th></tr>"]
    for k in KINDS:
        st, cls, _ = STATUS[k]
        first = True
        for ds in DATASETS:
            c = C[ds][k]
            if c["gold"] == 0 and c["fp"] + c["fp_rev"] == 0 and ds == "SYN" and k in ("wrong_tool_object", "parameter_deviation"):
                continue  # not tested on this set
            prec = pct(c["tp"], c["tp"] + c["fp"]) if (c["tp"] + c["fp"]) else "–"
            rec = pct(c["tp"], c["gold"]) if c["gold"] else "no labelled cases"
            summ.append("<tr>" + (f"<td rowspan='{{RS}}'><a href='#{k}'>{esc(TITLE[k])}</a></td><td rowspan='{{RS}}'><span class='pill {cls}'>{esc(st)}</span></td>" if first else "")
                        + f"<td>{DATASETS[ds]['short']}</td><td>{c['gold']}</td><td>{c['tp']}</td><td>{('–' if not (c['tp_rev'] or c['fp_rev']) else ', '.join(x for x in ((f"{c['tp_rev']} real" if c['tp_rev'] else ''), (f"{c['fp_rev']} false" if c['fp_rev'] else '')) if x))}</td>"
                        f"<td>{c['fp']}</td><td>{c['fn']}</td><td>{prec}</td><td>{rec}</td></tr>")
            first = False
        n_rows = sum(1 for ds in DATASETS if not (C[ds][k]["gold"] == 0 and C[ds][k]["fp"] + C[ds][k]["fp_rev"] == 0 and ds == "SYN" and k in ("wrong_tool_object", "parameter_deviation")))
        for i in range(len(summ) - 1, -1, -1):
            if "{RS}" in summ[i]:
                summ[i] = summ[i].replace("{RS}", str(n_rows))
                break
    summ.append("</table>")
    parts.append("\n".join(summ))

    # --- per kind sections ---
    for k in KINDS:
        st, cls, mode = STATUS[k]
        what, how = ABOUT[k]
        sec = [f"<section id='{k}' class='kind'><h2>{esc(TITLE[k])} <span class='pill {cls}'>{esc(st)}</span></h2>",
               f"<p class='lead'><b>What it is.</b> {esc(what)} <b>How it is checked.</b> {esc(how)}</p>",
               f"<p class='mode'><b>Recommended deployment:</b> {esc(mode)}</p>"]
        sec.append("<table class='mini'><tr><th>Test set</th><th>Labelled</th><th>Caught</th><th>Caught, sent to review</th><th>False alarms</th><th>False alarms sent to review</th><th>Missed</th></tr>")
        for ds in DATASETS:
            c = C[ds][k]
            sec.append(f"<tr><td>{DATASETS[ds]['short']}</td><td>{c['gold']}</td><td>{c['tp']}</td><td>{c['tp_rev']}</td><td>{c['fp']}</td><td>{c['fp_rev']}</td><td>{c['fn']}</td></tr>")
        sec.append("</table>")
        pc = PREV_C.get(k)
        if pc and pc["gold"]:
            sec.append(f"<p class='prev'>{esc(PREVIOUS['label'])}: caught {pc['tp']}, caught but sent to review {pc['tp_rev']}, "
                       f"false alarms {pc['fp']} (plus {pc['fp_rev']} sent to review), missed {pc['fn']}, of {pc['gold']} labelled.</p>")
        sec.append("<h3>Scenarios</h3><div class='scen'>")
        for ds, eid, kind, step, outcome, what_h, why_h in SCEN[k]:
            gold, V = data[ds]
            fr = frames_for(ds, eid, kind, step, outcome, V, gold)
            lab, oc = OUTCOME[outcome]
            sec.append(f"<div class='card'><div class='head'><span class='pill {oc}'>{esc(lab)}</span> <span class='src'>{esc(DATASETS[ds]['short'])} · {esc(eid)}</span></div>"
                       f"<div class='frames'>" + "".join(f"<figure><img src='data:image/jpeg;base64,{j}'><figcaption>{t} s</figcaption></figure>" for t, j in fr) + "</div>"
                       f"<p>{esc(what_h)}</p>" + (f"<p class='why'><b>Why:</b> {esc(why_h)}</p>" if why_h else "") + "</div>")
        sec.append("</div>")
        sec.append("<h3>Why it works or is hard</h3><ul>" + "".join(f"<li>{esc(w)}</li>" for w in WHY[k]) + "</ul>")
        sec.append(f"<p><b>What would fix it:</b> {esc(FIX[k])}</p></section>")
        parts.append("\n".join(sec))

    meta = {"clean": clean}
    body = "\n".join(parts)
    page = TEMPLATE.replace("{{BODY}}", body)
    page = page.replace("{{CLEAN_CC}}", f"{clean['CC'][0]} of {clean['CC'][1]}")
    page = page.replace("{{SYN_ABOUT}}", esc(DATASETS["SYN"]["about"])).replace("{{SYN_VER}}", esc(DATASETS["SYN"]["version"]))
    page = page.replace("{{CC_ABOUT}}", esc(DATASETS["CC"]["about"])).replace("{{CC_VER}}", esc(DATASETS["CC"]["version"]))
    Path(a.out).write_text(page)
    print(f"wrote {a.out} ({Path(a.out).stat().st_size / 1e6:.1f} MB)")
    for ds in DATASETS:
        print(ds, {k: C[ds][k] for k in KINDS}, "clean flagged", clean[ds])


TEMPLATE = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Procedural-error AutoQC: which error kinds are ready to deploy</title>
<style>
:root{--bg:#0f1216;--panel:#171b21;--panel2:#1e242c;--line:#2a323d;--text:#e6e9ee;--muted:#98a2b3;--go:#3ccf91;--caution:#f5b942;--stop:#ff5d6c;--acc:#4fa3ff}
@media (prefers-color-scheme: light){:root{--bg:#f6f7f9;--panel:#fff;--panel2:#eef1f5;--line:#d7dde6;--text:#1a2230;--muted:#5b6676}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif}
header,main{max-width:1180px;margin:0 auto;padding:20px 28px}header{border-bottom:1px solid var(--line)}h1{font-size:22px;margin:0 0 6px}
.sub{color:var(--muted);font-size:14px}.banner{background:var(--panel2);border:1px solid var(--line);border-left:4px solid var(--caution);border-radius:10px;padding:10px 14px;margin:14px 0;font-size:14px}
table{border-collapse:collapse;width:100%;font-size:13.5px;background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{padding:7px 9px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}
.ci{color:var(--muted);font-size:12px}.pill{display:inline-block;font-size:12px;padding:2px 9px;border-radius:999px;border:1px solid;white-space:nowrap}
.pill.go{color:var(--go);border-color:var(--go)}.pill.caution{color:var(--caution);border-color:var(--caution)}.pill.stop{color:var(--stop);border-color:var(--stop)}
a{color:var(--acc)}section.kind{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin:18px 0}
section.kind h2{margin:0 0 8px;font-size:19px}.lead{margin:6px 0}.mode{background:var(--panel2);border-radius:8px;padding:8px 10px}
table.mini{margin:8px 0 4px}h3{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:16px 0 8px}
.scen{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:12px}.card{background:var(--panel2);border:1px solid var(--line);border-radius:12px;padding:10px 12px}
.card .head{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:6px}.src{color:var(--muted);font-size:12px;font-family:ui-monospace,Menlo,monospace}
.frames{display:flex;gap:6px}.frames figure{margin:0;flex:1;text-align:center;font-size:11px;color:var(--muted)}.frames img{width:100%;border-radius:6px;border:1px solid var(--line);display:block}
.card p{margin:6px 0;font-size:13.5px}.why{color:var(--muted)}ul{margin:4px 0 8px 18px;padding:0}li{margin:3px 0}
.prev{color:var(--muted);font-size:13px;margin:4px 0}.legend{display:grid;grid-template-columns:max-content 1fr;gap:4px 12px;font-size:13.5px;margin-top:8px}
</style></head><body>
<header><h1>Procedural-error AutoQC: which error kinds are ready to deploy</h1>
<div class="sub">Evidence from two test sets, measured 24–28 Sep 2026. Every count on this page comes from the pipeline's stored results scored against labels; scenario explanations are written from the same results.</div>
<div class="banner"><b>Read these numbers as direction, not certification.</b> Each kind has between 1 and 19 labelled cases, so the 95 % intervals are wide. Both sets were measured with the current pipeline; the previous version's synthetic results are shown for comparison in each section. A kind marked ready means ready to flag for a human, not to act without one.</div>
<div class="legend"><b>Caught</b><span>the pipeline confirmed an error that the labels contain.</span><b>Sent to review</b><span>the pipeline raised it but the adjudicator was not confident; a human decides.</span><b>False alarm</b><span>the pipeline confirmed an error the labels do not contain (some are real but unlabelled; noted where so).</span><b>Missed</b><span>a labelled error the pipeline did not raise at all.</span></div>
</header>
<main>
<h2 style="font-size:18px">Summary</h2>
{{BODY}}
<section class="kind"><h2>How this was measured</h2>
<p><b>Synthetic set.</b> {{SYN_ABOUT}} Measured with the {{SYN_VER}}.</p>
<p><b>Real set.</b> {{CC_ABOUT}} Measured with the {{CC_VER}}. Clean recordings falsely flagged: {{CLEAN_CC}}.</p>
<p><b>Scoring.</b> A finding counts as caught when its error kind and step match a label. Early termination is matched by kind (an episode terminates once). Off-procedure additions have no step, so they are matched by time overlap. Wrong-tool and parameter labels exist only in the real set.</p>
<p><b>Cost and speed (current pipeline).</b> Real set: about $0.31 per 11-minute recording ($0.27 narration and judges, $0.04 adjudication); narration about 56 s per recording (median), adjudication about 22 s. Synthetic set (about 1-minute recordings): $0.10 per recording and 52 s end to end (median; 95th percentile 109 s): narration 27 s, the seven judges in parallel 12 s, adjudication 21 s.</p>
<p><b>What is not tested yet.</b> Correction loops; wrong tool and parameter deviation on the synthetic set (they cannot be made by re-cutting video); early termination, off-procedure additions and repeats on real recordings (the real set has none labelled); annotator mistakes (planned separately).</p>
</section>
</main></body></html>"""

if __name__ == "__main__":
    main()
