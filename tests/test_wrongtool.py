"""Wrong tool / object: closed-question tally, relation rule, grouping and helpers (no model calls)."""
import numpy as np

from procqc.judges import wrongtool as W
from procqc.judges.base import CONFIRMED, REVIEW

CARD = {"specified_item": "item a", "confusables": ["item b", "item c"], "role": "tool", "item_id": "item_a",
        "role_description": "what the action is done with", "form": "", "base_item": "item a"}


def _a(picked, named=""):
    return {"picked": picked, "named_item": named, "evidence": ""}


def test_relation_rule():
    t = W.tally([_a("item b")] * 3, CARD)  # a listed look-alike, unanimous
    assert W.decide(t, "different", None) == CONFIRMED
    assert W.decide(t, "broader", None) == CONFIRMED  # chosen over the specified item
    assert W.decide(t, "kind_of", None) is None and W.decide(t, "same", None) is None
    assert W.decide(t, "not_in_role", None) is None
    assert W.decide(t, "sibling", "s9") == REVIEW  # another step's own item
    o = W.tally([_a(W.OTHER, "general term")] * 3, CARD)
    assert W.decide(o, "broader", None) is None  # a general name for what may be the specified item
    assert W.decide(o, "other_form", None) == CONFIRMED  # another form is another object
    h = W.tally([_a(W.NO_OBJECT)] * 3, CARD)
    assert W.decide(h, None, None) == CONFIRMED
    two = W.tally([_a("item b"), _a("item b"), _a("item a")], CARD)
    assert W.decide(two, "different", None) == REVIEW
    assert W.decide(W.tally([_a("item a")] * 2, CARD), None, None) is None
    assert W.decide(W.tally([_a(W.CANNOT)] * 3, CARD), None, None) is None


def test_relations_cover_rule():
    assert W.NO_FLAG | W.FLAG | {"broader"} == set(W.RELATIONS)
    assert set(W.RELATION_SCHEMA["properties"]["relation"]["enum"]) == set(W.RELATIONS)


def test_group_one_finding_per_substitute():
    def chk(step, used, status, t0):
        return {"step": step, "status": status, "card": CARD, "window_s": [t0, t0 + 5], "zoom": {"window_s": [t0, t0 + 1]},
                "tally": {"answer": used, "votes": 3, "of": 3}, "answers": [], "other_step": None,
                "relation": {"relation": "different"}}
    checks = [chk("s3", "item b", REVIEW, 30), chk("s1", "Item B", CONFIRMED, 10), chk("s2", "item c", REVIEW, 20),
              {"step": "s4", "result": "not_seen", "card": CARD}]
    c = W.group(checks, {"s1": [(-1, 10, 15)], "s2": [(-1, 20, 25)], "s3": [(-1, 30, 35)]})
    b = next(x for x in c if x["used"].lower() == "item b")
    assert len(c) == 2 and b["step"] == "s1" and b["also_steps"] == ["s3"] and b["status"] == CONFIRMED


def test_options_keep_fixed_answers_last_and_cap_items():
    card = dict(CARD, confusables=["b", "c", "d", "e", "f", "g", "item a"])
    opts = W.options_for(card)
    assert opts[0] == "item a" and opts[-3:] == [W.NO_OBJECT, W.OTHER, W.CANNOT] and len(opts) == 8


def test_other_step_item_and_masking():
    cards = {"s1": [CARD], "s2": [{"specified_item": "part x", "base_item": "part x", "item_id": "part_x"}]}
    assert W.other_step_item("a part x", "item a", cards) == "s2"
    assert W.other_step_item("unknown thing", "item a", cards) is None
    from procqc.graph.schema import Node
    assert "item" not in W.neutral_action(Node(id="s1", name="s1", description="Use the item a on it"), CARD).replace("[item]", "")


def test_windows_and_boxes():
    assert W.step_window([(0, 10.0, 15.0)], 100.0) == [9.0, 16.0]
    assert W.step_window([(0, 10.0, 10.5)], 100.0) == [8.75, 11.75]  # widened to MIN_SPAN around the middle
    assert W.step_window([(0, 0.2, 0.4)], 100.0)[0] == 0.0
    assert W.dense_window([1.0, 2.0], 1.8) == [0.5, 1.8]
    assert len(W.scan_times([0.0, 100.0])) == W.SCAN_MAX and len(W.scan_times([0.0, 1.0])) == 4
    assert W.to_pixels([100, 200, 300, 400], (1000, 2000)) == (400.0, 100.0, 800.0, 300.0)
    assert W.to_pixels([0, 0, 1, 1], (100, 100)) is None and W.to_pixels(None, (100, 100)) is None


def test_contact_sheets_tile_and_number():
    frames = [(np.zeros((90, 160, 3), dtype=np.uint8), float(i)) for i in range(18)]
    sheets = W.contact_sheets(frames)
    assert len(sheets) == 2 and sheets[0].shape[1] == W.TILE_W * W.SHEET_COLS
    assert sheets[1].shape[0] == sheets[0].shape[0] // 4  # 2 tiles on the second sheet: one row


def test_crop_enlarges_to_edge():
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    c = W.crop(img, (100, 100, 150, 140))
    assert max(c.shape[:2]) == W.CROP_EDGE
