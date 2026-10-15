"""Demo builder on a tiny synthetic run (no model calls, no video)."""
import json

from procqc.demo import build as B

GRAPH = """task_id: t
name: Tiny task
nodes:
  - {id: start, name: Start, kind: start}
  - {id: s1, name: a, description: Do a}
  - {id: s2, name: b, description: Do b}
  - {id: end, name: End, kind: end}
edges:
  - {source: start, target: s1}
  - {source: s1, target: s2}
  - {source: s2, target: end}
"""


def _write(tmp_path):
    (tmp_path / "g.yaml").write_text(GRAPH)
    (tmp_path / "run" / "episodes").mkdir(parents=True)
    flag = {"step": "s1", "status": "confirmed", "span_s": [1, 2],
            "verification": {"explanation": "not seen", "verdict": "omitted"}}
    routed = {"step": "s2", "status": "rejected", "span_s": [3, 4], "routed": "verifier rejected"}
    dropped = {"span_s": [5, 6], "status": "rejected"}
    eps = {
        "a": {"omission": {"candidates": [flag, dict(routed, routed=None)], "flags": [flag], "review": [routed]},
              "offgraph": {"candidates": [dropped], "flags": [], "review": []}},
        "b": {"omission": {"candidates": [], "flags": [], "review": []}},
    }
    for eid, checks in eps.items():
        (tmp_path / "run" / "episodes" / f"{eid}.json").write_text(json.dumps(
            {"episode_id": eid, "duration_s": 10, "checks": checks}))
    (tmp_path / "labels.jsonl").write_text(json.dumps({"episode_id": "a", "findings": [
        {"kind": "omission", "step": "s1", "start": 1, "end": 2}, {"kind": "addition_offgraph", "start": 5, "end": 6}]}) + "\n")
    (tmp_path / "manifest.jsonl").write_text("".join(json.dumps({"episode_id": e, "video": str(tmp_path / f"{e}.mp4"),
                                                                 "graph": str(tmp_path / "g.yaml")}) + "\n" for e in eps))
    return {"title": "t", "datasets": [{"name": "D", "run_dir": str(tmp_path / "run"), "labels": str(tmp_path / "labels.jsonl"),
                                        "manifest": str(tmp_path / "manifest.jsonl"), "splits": {"*": {"a": "dev"}}}]}


def test_build_statuses_outcomes_and_metrics(tmp_path):
    data = B.build(_write(tmp_path), tmp_path / "site")
    rec = {r["episode_id"]: r for r in data["recordings"]}
    om = rec["a"]["kinds"]["omission"]
    assert [e["status"] for e in om["events"]] == ["flagged", "review"]  # the routed copy is not shown twice
    assert om["events"][0]["outcome"] == "match" and om["events"][1]["outcome"] == "false_alarm"
    assert om["events"][0]["explanation"] == "not seen" and om["verdict"] == "flagged" and om["split"] == "dev"
    off = rec["a"]["kinds"]["addition_offgraph"]
    assert [e["status"] for e in off["events"]] == ["dropped"] and off["events"][0]["outcome"] == "would_match"
    assert off["verdict"] == "clean" and off["gold"][0]["hit"] is False
    assert rec["b"]["kinds"]["omission"]["verdict"] == "clean" and rec["b"]["kinds"]["omission"]["split"] == "all"
    assert rec["a"]["steps"] == [["s1", "Do a"], ["s2", "Do b"]] and rec["a"]["task"] == "Tiny task"
    m = next(x for x in data["metrics"] if x["kind"] == "omission" and x["split"] == "all")
    assert m["flags"]["recording"]["tp"] == 1 and m["flags"]["recording"]["tn"] == 1 and m["flags + review"]["event"]["fp"] == 1
    assert {x["split"] for x in data["metrics"] if x["kind"] == "omission"} == {"all", "dev"}
    for f in ("index.html", "data.js", "videos.json"):
        assert (tmp_path / "site" / f).exists()
    assert len(json.loads((tmp_path / "site" / "videos.json").read_text())) == 2
