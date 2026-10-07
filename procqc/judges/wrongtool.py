"""Wrong tool / object / ingredient: per step, find the moment, zoom in, identify with a closed question,
then classify how the observed item relates to the specified one. All calls are frame and text calls via
Fuelix.

Items (one text call per procedure): a card per item each timed step names (role, a description of where
to look that does not give the item away, the specified item, its base item and form, its appearance, its
look-alikes), plus a card for the tool or destination a step's action implies when the step names none.

Per card, at every step the narration (or a reference timing) shows performed:
  1. moment    numbered contact sheets of the step at 2 frames/s (up to 32 small tiles): in which tiles is
               the action seen with the hand or gripper on whatever fills the role.
  2. zoom      dense frames at 4 frames/s around those tiles (up to 6), and one box around the hand AND the
               object it uses on 2 of them, cropped and enlarged.
  3. identify  a closed question, asked up to 3 times with the options in a new order each time (it stops
               early once two answers agree on the specified item): the specified item, its look-alikes,
               "bare hand or gripper, no object", "something else" (named), "cannot tell". The expected item
               is never marked. Confidence is agreement across the asks (no answer probabilities available).
  4. relation  for a majority on another item: a lexical relation to the specified item, then a fixed rule:
                 same / kind_of / not_in_role   -> no flag
                 broader                        -> no flag, unless it was picked from the listed look-alikes
                 sibling / other_form / different, or a bare hand where an object is named or implied -> flag
  status       all 3 asks agree and the observed item is not another step's own item -> confirmed;
               otherwise needs_review. Flags of the same substitute for the same item are one finding that
               lists every step.
Sibling policy (user decision): one variety of an item for another is an error.
"""
from __future__ import annotations

import base64
import contextvars
import random
import re
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Sequence

import numpy as np

from procqc import pricing, prompts
from procqc.config import config
from procqc.graph.schema import TaskGraph
from procqc.judges.base import CONFIRMED, REVIEW, Episode
from procqc.judges.narration import performed_spans

KIND = "wrong_tool_object"
STAGE = "wrongtool"
EFFORT = "low"
CHECK_ROLES = ("tool", "container", "ingredient", "target")  # appliances are not substituted in practice
PAD, MIN_SPAN = 1.0, 3.0                                       # step window around the narrated entries
SCAN_FPS, SCAN_MAX, TILE_W, SHEET_COLS, SHEET_TILES = 2.0, 32, 240, 4, 16
DENSE_FPS, DENSE_MAX, DENSE_PAD = 4.0, 6, 0.5
CROP_PAD, CROP_EDGE = 0.3, 512
K_ASKS = 3
NO_OBJECT, OTHER, CANNOT = "bare hand or gripper, no object", "something else", "cannot tell"
RELATIONS = ("same", "kind_of", "broader", "not_in_role", "sibling", "other_form", "different")
NO_FLAG = {"same", "kind_of", "not_in_role"}
FLAG = {"sibling", "other_form", "different"}


def model() -> str:
    return config.text_model


# ------------------------------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------------------------------
def _norm(x) -> str:
    return " ".join(re.findall(r"[a-z]+", str(x or "").lower()))


def _stem(w: str) -> str:
    return re.sub(r"(?:es|s)$", "", w) if len(w) > 3 else w


def _words(x) -> set:
    return {_stem(w) for w in _norm(x).split()}


def neutral_action(n, card: dict) -> str:
    """The step text with the specified item and its base item masked, so the question does not give it away."""
    text = n.description or n.name
    words = {card.get("specified_item", ""), card.get("base_item", "")}
    words |= {w for x in list(words) for w in x.split()}
    for w in sorted(words, key=len, reverse=True):
        if len(w) > 2 and w.lower() not in ("the", "and", "with", "into", "from"):
            text = re.sub(re.escape(w), "[item]", text, flags=re.I)
    return text


def other_step_item(observed: str, item_id: str, cards: Dict[str, List[dict]]) -> Optional[str]:
    """The step whose own item the observed object is (all words of that step's base item appear in the
    observed name), other than the item being checked; None if there is none."""
    ow = _words(observed)
    for sid, cs in cards.items():
        for c in cs:
            if _norm(c.get("item_id") or c["specified_item"]) == item_id:
                continue
            bw = _words(c.get("base_item") or c["specified_item"])
            if bw and bw <= ow:
                return sid
    return None


def step_window(entries: Sequence[tuple], duration: float) -> List[float]:
    a, b = min(e[1] for e in entries) - PAD, max(e[2] for e in entries) + PAD
    if b - a < MIN_SPAN:
        m = (a + b) / 2
        a, b = m - MIN_SPAN / 2, m + MIN_SPAN / 2
    return [max(0.0, a), min(duration, b)]


def reference_spans(steps: Dict[str, List[List[float]]]) -> Dict[str, List[tuple]]:
    """Step times from a reference timing in the narration spans' shape: step -> [(-1, start, end)]."""
    return {sid: [(-1, float(a), float(b)) for a, b in ab] for sid, ab in steps.items()}


def keyframes(video_path: str, window: Sequence[float], n: int) -> List[tuple]:
    from procqc.signals.frames import VideoReader
    a, b = window
    times = [a + (b - a) * (i + 0.5) / n for i in range(n)]
    with VideoReader(video_path) as v:
        fr = v.frames_at(times)
    return [(f, t) for f, t in zip(fr, times) if f is not None]


def jpeg_url(img: np.ndarray, long_edge: Optional[int] = None, quality: int = 90) -> str:
    import cv2
    if long_edge and max(img.shape[:2]) > long_edge:
        s = long_edge / max(img.shape[:2])
        img = cv2.resize(img, (int(img.shape[1] * s), int(img.shape[0] * s)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


def to_pixels(box_2d, shape) -> Optional[tuple]:
    """Gemini box_2d [ymin, xmin, ymax, xmax] on a 0-1000 grid -> pixel (x1, y1, x2, y2)."""
    try:
        y1, x1, y2, x2 = (float(v) for v in box_2d)
    except (TypeError, ValueError):
        return None
    H, W = shape[:2]
    x1, x2 = sorted((x1, x2))
    y1, y2 = sorted((y1, y2))
    if x2 - x1 < 5 or y2 - y1 < 5:
        return None
    return (x1 / 1000 * W, y1 / 1000 * H, x2 / 1000 * W, y2 / 1000 * H)


def crop(img: np.ndarray, box, pad: float = CROP_PAD, edge: int = CROP_EDGE) -> np.ndarray:
    import cv2
    H, W = img.shape[:2]
    x1, y1, x2, y2 = box
    px, py = (x2 - x1) * pad, (y2 - y1) * pad
    a = img[int(max(0, y1 - py)):int(min(H, y2 + py)), int(max(0, x1 - px)):int(min(W, x2 + px))]
    if a.size == 0:
        return img
    s = edge / max(a.shape[:2])  # enlarge small crops so the model spends its tokens on the item
    return cv2.resize(a, (max(1, int(a.shape[1] * s)), max(1, int(a.shape[0] * s))), interpolation=cv2.INTER_CUBIC)


def _call(text_client, system: str, content: list, schema: dict, name: str, stage: str) -> dict:
    with pricing.timed_stage(stage):
        d = text_client.complete_json_messages([{"role": "system", "content": system}, {"role": "user", "content": content}],
                                               schema=schema, schema_name=name, model=model(), max_tokens=4000,
                                               reasoning_effort=EFFORT)
    if isinstance(d, list):
        d = next((x for x in d if isinstance(x, dict)), {})
    return d if isinstance(d, dict) else {}


# ------------------------------------------------------------------------------------------
# items
# ------------------------------------------------------------------------------------------
CARD_SCHEMA = {
    "type": "object",
    "properties": {"cards": {"type": "array", "items": {
        "type": "object",
        "properties": {"step_id": {"type": "string"}, "item_id": {"type": "string"}, "role": {"type": "string"},
                       "role_description": {"type": "string"},
                       "specified_item": {"type": "string"}, "appearance": {"type": "string"},
                       "confusables": {"type": "array", "items": {"type": "string"}},
                       "base_item": {"type": "string"}, "form": {"type": "string"}, "implied": {"type": "boolean"}},
        "required": ["step_id", "item_id", "role", "role_description", "specified_item", "appearance",
                     "confusables", "base_item", "form", "implied"]}}},
    "required": ["cards"],
}


def item_cards(g: TaskGraph, text_client) -> Dict[str, List[dict]]:
    steps = "\n".join(f"  [{n.id}] {n.description or n.name}" for n in g.nodes if n.is_step)
    with pricing.timed_stage(f"{STAGE}_cards"):
        data = text_client.complete_json(prompts.get("wrongtool.cards.system"), f"TASK: {g.name}\nSTEPS:\n{steps}\n\nReturn the cards.",
                                         schema=CARD_SCHEMA, schema_name="cards", model=model(), max_tokens=12000,
                                         reasoning_effort=EFFORT)
    ids = {n.id for n in g.nodes if n.is_step}
    out: Dict[str, List[dict]] = {}
    for c in (data.get("cards") or [] if isinstance(data, dict) else []):
        s = str(c.get("step_id", "")).strip("[] ")
        if s in ids and c.get("specified_item") and str(c.get("role", "")).lower() in CHECK_ROLES:
            c.setdefault("base_item", c["specified_item"])
            c.setdefault("form", "")
            c["implied"] = bool(c.get("implied"))
            c["confusables"] = [x for x in c.get("confusables") or [] if _norm(x) != _norm(c["specified_item"])]
            if not any(_norm(c.get("item_id", "")) == _norm(o.get("item_id", "")) for o in out.get(s, [])):
                out.setdefault(s, []).append(c)
    return out


# ------------------------------------------------------------------------------------------
# 1. moment
# ------------------------------------------------------------------------------------------
MOMENT_SCHEMA = {"type": "object",
                 "properties": {"tiles": {"type": "array", "items": {"type": "integer"}},
                                "best_tile": {"type": "integer"}, "seen": {"type": "boolean"}},
                 "required": ["tiles", "best_tile", "seen"]}


def scan_times(window: Sequence[float]) -> List[float]:
    a, b = window
    n = int(min(SCAN_MAX, max(4, round((b - a) * SCAN_FPS))))
    return [a + (b - a) * (i + 0.5) / n for i in range(n)]


def contact_sheets(frames: List[tuple]) -> List[np.ndarray]:
    """Frames -> sheets of numbered tiles (4 columns, up to 16 tiles each), numbered from 1."""
    import cv2
    sheets = []
    for s in range(0, len(frames), SHEET_TILES):
        chunk = frames[s:s + SHEET_TILES]
        tiles = []
        for k, (f, _) in enumerate(chunk, s + 1):
            h = int(f.shape[0] * TILE_W / f.shape[1])
            t = cv2.resize(f, (TILE_W, h), interpolation=cv2.INTER_AREA)
            cv2.rectangle(t, (0, 0), (34, 20), (0, 0, 0), -1)
            cv2.putText(t, str(k), (3, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
            tiles.append(t)
        h = tiles[0].shape[0]
        while len(tiles) % SHEET_COLS:
            tiles.append(np.zeros((h, TILE_W, 3), dtype=np.uint8))
        rows = [np.hstack(tiles[i:i + SHEET_COLS]) for i in range(0, len(tiles), SHEET_COLS)]
        sheets.append(np.vstack(rows))
    return sheets


def find_moment(ctx: str, video_path: str, window: Sequence[float], text_client) -> dict:
    times = scan_times(window)
    frames = keyframes(video_path, window, len(times))
    sheets = contact_sheets(frames)
    content: list = [{"type": "text", "text": ctx + f"\n{len(frames)} tiles on {len(sheets)} sheet(s), "
                                                  f"{(window[1] - window[0]) / max(1, len(frames)):.1f} s apart."}]
    for sh in sheets:
        content.append({"type": "image_url", "image_url": {"url": jpeg_url(sh, 1024, 85)}})
    content.append({"type": "text", "text": "Return the JSON."})
    m = _call(text_client, prompts.get("wrongtool.moment.system"), content, MOMENT_SCHEMA, "moment", f"{STAGE}_moment")
    ts = [f[1] for f in frames]
    tiles = sorted({int(t) for t in (m.get("tiles") or []) if 1 <= int(t) <= len(ts)})
    best = int(m.get("best_tile") or 0)
    if not (1 <= best <= len(ts)):
        best = tiles[len(tiles) // 2] if tiles else 0
    seen = bool(m.get("seen")) and bool(tiles or best)
    out = {"n_tiles": len(ts), "tiles": tiles, "best_tile": best, "seen": seen}
    if seen:
        # the run of tiles around the best one (other runs are other uses: the first use is not assumed)
        run = [best]
        while run[0] - 1 in tiles:
            run.insert(0, run[0] - 1)
        while run[-1] + 1 in tiles:
            run.append(run[-1] + 1)
        out["span_s"] = [round(ts[run[0] - 1], 2), round(ts[run[-1] - 1], 2)]
        out["best_s"] = round(ts[best - 1], 2)
    return out


# ------------------------------------------------------------------------------------------
# 2. zoom
# ------------------------------------------------------------------------------------------
LOCATE_SCHEMA = {"type": "object",
                 "properties": {"frames": {"type": "array", "items": {"type": "object", "properties": {
                     "frame": {"type": "integer"}, "box": {"type": ["array", "null"], "items": {"type": "number"}}},
                     "required": ["frame", "box"]}}},
                 "required": ["frames"]}


def dense_window(span: Sequence[float], duration: float) -> List[float]:
    return [max(0.0, span[0] - DENSE_PAD), min(duration, span[1] + DENSE_PAD)]


def dense_count(win: Sequence[float]) -> int:
    return int(min(DENSE_MAX, max(3, round((win[1] - win[0]) * DENSE_FPS))))


def zoom(ctx: str, video_path: str, win: Sequence[float], text_client) -> dict:
    frames = keyframes(video_path, win, dense_count(win))
    mids = list(range(len(frames)))[max(0, len(frames) // 2 - 1):][:2]
    content: list = [{"type": "text", "text": ctx}]
    for j, k in enumerate(mids, 1):
        content += [{"type": "text", "text": f"frame {j}:"},
                    {"type": "image_url", "image_url": {"url": jpeg_url(frames[k][0])}}]
    content.append({"type": "text", "text": "Return the JSON."})
    loc = _call(text_client, prompts.get("wrongtool.locate.system"), content, LOCATE_SCHEMA, "locate", f"{STAGE}_locate")
    byj = {int(x.get("frame", 0)): x for x in loc.get("frames", []) or [] if isinstance(x, dict)}
    crops = []
    for j, k in enumerate(mids, 1):
        b = to_pixels((byj.get(j) or {}).get("box"), frames[k][0].shape)
        if b:
            crops.append((crop(frames[k][0], b), frames[k][1]))
    return {"frames": frames, "crops": crops, "n_boxes": len(crops)}


# ------------------------------------------------------------------------------------------
# 3. identify (closed, shuffled, asked up to K_ASKS times)
# ------------------------------------------------------------------------------------------
IDENTIFY_SCHEMA = {"type": "object",
                   "properties": {"choice": {"type": "string"}, "named_item": {"type": "string"},
                                  "evidence": {"type": "string"}},
                   "required": ["choice", "named_item", "evidence"]}


def options_for(card: dict) -> List[str]:
    opts = [card["specified_item"]]
    for c in card.get("confusables") or []:
        c = str(c).strip()
        if c and _norm(c) not in {_norm(o) for o in opts} and len(opts) < 5:
            opts.append(c)
    return opts + [NO_OBJECT, OTHER, CANNOT]


def identify(ctx: str, card: dict, z: dict, text_client, seed: int) -> List[dict]:
    opts = options_for(card)
    images: list = []
    for f, t in z["frames"]:
        images += [{"type": "text", "text": f"frame @ {t:.2f}s:"},
                   {"type": "image_url", "image_url": {"url": jpeg_url(f)}}]
    for c, t in z["crops"]:
        images += [{"type": "text", "text": f"enlarged crop @ {t:.2f}s:"},
                   {"type": "image_url", "image_url": {"url": jpeg_url(c)}}]
    rng = random.Random(seed)
    answers = []
    for k in range(K_ASKS):
        head = opts[:-3]
        rng.shuffle(head)
        order = head + opts[-3:]  # the fixed options stay last, so they are not confused with items
        letters = "ABCDEFGH"[:len(order)]
        listing = "\n".join(f"{l}) {o}" for l, o in zip(letters, order))
        content = [{"type": "text", "text": ctx + f"\nOPTIONS:\n{listing}"}] + images + [{"type": "text", "text": "Return the JSON."}]
        a = _call(text_client, prompts.get("wrongtool.identify.system"), content, IDENTIFY_SCHEMA, "identify",
                  f"{STAGE}_identify")
        letter = str(a.get("choice", "")).strip().upper()[:1]
        picked = order[letters.index(letter)] if letter and letter in letters else CANNOT
        answers.append({"ask": k, "order": order, "choice": letter, "picked": picked,
                        "named_item": a.get("named_item", ""), "evidence": a.get("evidence", "")})
        if sum(x["picked"] == card["specified_item"] for x in answers) >= 2:
            break  # two asks agree it is the specified item: a third cannot change the outcome
    return answers


def tally(answers: List[dict], card: dict) -> dict:
    """Majority over the asks. 'something else' answers are grouped by their named item."""
    keys = [(_norm(a["named_item"]) if a["picked"] == OTHER else _norm(a["picked"])) or "cannot tell" for a in answers]
    top, n = Counter(keys).most_common(1)[0]
    pick = next(a for a, k in zip(answers, keys) if k == top)
    kind = ("specified" if pick["picked"] == card["specified_item"] else
            "cannot" if pick["picked"] == CANNOT else "other" if pick["picked"] == OTHER else
            "no_object" if pick["picked"] == NO_OBJECT else "confusable")
    return {"answer": pick["named_item"] if kind == "other" else pick["picked"], "kind": kind, "votes": n,
            "of": len(answers), "majority": n * 2 > len(answers)}


# ------------------------------------------------------------------------------------------
# 4. relation and decision
# ------------------------------------------------------------------------------------------
RELATION_SCHEMA = {"type": "object",
                   "properties": {"relation": {"type": "string", "enum": list(RELATIONS)}, "reason": {"type": "string"}},
                   "required": ["relation", "reason"]}

_REL_CACHE: Dict[tuple, dict] = {}
_REL_LOCK = threading.Lock()


def relation(card: dict, step_text: str, observed: str, text_client) -> dict:
    key = (_norm(card["specified_item"]), _norm(card.get("form", "")), card.get("role"), _norm(observed), _norm(step_text))
    with _REL_LOCK:
        if key in _REL_CACHE:
            return _REL_CACHE[key]
    user = (f"STEP: {step_text}\nROLE ({card['role']}): {card['role_description']}\n"
            f"SPECIFIED: {card['specified_item']} (base item: {card.get('base_item') or card['specified_item']}; "
            f"form named by the step: {card.get('form') or 'none'}"
            f"{'; not named by the step, implied by its action' if card.get('implied') else ''})\n"
            f"OBSERVED: {observed}\nReturn the JSON.")
    with pricing.timed_stage(f"{STAGE}_relation"):
        r = text_client.complete_json(prompts.get("wrongtool.relation.system"), user, schema=RELATION_SCHEMA,
                                      schema_name="relation", model=model(), max_tokens=2000, reasoning_effort=EFFORT)
    r = r if isinstance(r, dict) and r.get("relation") in RELATIONS else {"relation": "different", "reason": "unparsed"}
    with _REL_LOCK:
        _REL_CACHE[key] = r
    return r


def decide(t: dict, rel: Optional[str], other_step: Optional[str]) -> Optional[str]:
    """Fixed rule over the tally and the relation. None = no flag."""
    if not t["majority"] or t["kind"] in ("specified", "cannot"):
        return None
    if t["kind"] != "no_object":
        if rel in NO_FLAG:
            return None
        if rel == "broader" and t["kind"] != "confusable":
            return None  # a general name for what may be the specified item; a listed look-alike chosen
            # over the specified item is a statement that it is not the specified item
    return CONFIRMED if t["votes"] == t["of"] == K_ASKS and not other_step else REVIEW


# ------------------------------------------------------------------------------------------
# per step and recording
# ------------------------------------------------------------------------------------------
def finish(g: TaskGraph, sid: str, card: dict, answers: List[dict], text_client, cards, out: dict) -> dict:
    """Tally, relation and status for a step's answers."""
    item = _norm(card.get("item_id") or card["specified_item"])
    t = tally(answers, card)
    out.update(answers=answers, tally=t)
    rel = None
    if t["majority"] and t["kind"] in ("confusable", "other"):
        r = relation(card, g.node_map[sid].description or g.node_map[sid].name, t["answer"], text_client)
        out["relation"] = r
        rel = r["relation"]
    other = other_step_item(t["answer"], item, cards) if t["kind"] != "no_object" else None
    out["other_step"] = other
    out["status"] = decide(t, rel, other)
    out["result"] = t["kind"]
    return out


def check_step(g: TaskGraph, sid: str, card: dict, video_path: str, window: Sequence[float], duration: float,
               text_client, cards: Dict[str, List[dict]]) -> dict:
    item = _norm(card.get("item_id") or card["specified_item"])
    ctx = f"TASK: {g.name}. ACTION: {neutral_action(g.node_map[sid], card)}\nROLE: {card['role_description']}."
    out = {"step": sid, "window_s": [round(window[0], 2), round(window[1], 2)], "card": card}
    m = find_moment(ctx, video_path, window, text_client)
    out["moment"] = m
    if not m["seen"]:
        out["result"] = "not_seen"
        return out
    win = dense_window(m["span_s"], duration)
    z = zoom(ctx, video_path, win, text_client)
    out["zoom"] = {"window_s": [round(win[0], 2), round(win[1], 2)], "n_frames": len(z["frames"]), "n_crops": z["n_boxes"]}
    seed = int.from_bytes(f"{sid}|{item}".encode()[:8].ljust(8, b"0"), "little")
    answers = identify(ctx, card, z, text_client, seed)
    return finish(g, sid, card, answers, text_client, cards, out)


def group(checks: List[dict], spans: Dict[str, list]) -> List[dict]:
    """One finding per substitute of an item: flagged steps in time order, the first one as the step."""
    by: Dict[tuple, List[dict]] = {}
    for c in checks:
        if c.get("status"):
            key = (_norm(c["card"].get("item_id") or c["card"]["specified_item"]), _norm(c["tally"]["answer"]))
            by.setdefault(key, []).append(c)
    first = lambda c: min((x[1] for x in spans.get(c["step"], [])), default=c["window_s"][0])  # noqa: E731
    cands = []
    for cs in by.values():
        cs = sorted(cs, key=first)
        best = next((c for c in cs if c["status"] == CONFIRMED), cs[0])
        cands.append({"kind": KIND, "step": cs[0]["step"],
                      "status": CONFIRMED if any(c["status"] == CONFIRMED for c in cs) else REVIEW,
                      "span_s": cs[0]["zoom"]["window_s"], "specified": cs[0]["card"]["specified_item"],
                      "used": best["tally"]["answer"], "role": cs[0]["card"]["role"],
                      "implied": cs[0]["card"].get("implied", False),
                      "votes": f"{best['tally']['votes']}/{best['tally']['of']}",
                      "relation": (best.get("relation") or {}).get("relation"),
                      "also_steps": [c["step"] for c in cs[1:]], "other_step": best["other_step"],
                      "evidence": [a["evidence"] for a in best["answers"]]})
    return cands


def check(ep: Episode, step_times: Optional[Dict[str, List[List[float]]]] = None, workers: int = 4) -> dict:
    """step_times: optional reference step timing {step id: [[start, end], ...]} replacing the narration's."""
    g = ep.graph
    if step_times is None:
        duration, narr, _ = ep.narrated()
        spans = performed_spans(g, narr)
    else:
        duration, spans = ep.duration, reference_spans(step_times)
    cards = item_cards(g, ep.text_client)
    todo = [(sid, card) for sid, cs in cards.items() if sid in spans for card in cs]
    ctxs = [contextvars.copy_context() for _ in todo]  # each thread keeps the caller's cost meter

    def one(sc):
        sid, card = sc
        return check_step(g, sid, card, ep.video_path, step_window(spans[sid], duration), duration, ep.text_client, cards)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        checks = list(ex.map(lambda ci: ci[0].run(one, ci[1]), zip(ctxs, todo)))
    return {"kind": KIND, "candidates": group(checks, spans), "checks": checks, "cards": cards,
            "timing": "narration" if step_times is None else "reference", "model": model()}
