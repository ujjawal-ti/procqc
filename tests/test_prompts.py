"""Every static system prompt is in the registry and is principles only: no examples, no example items."""
import re

import pytest

from procqc import prompts
from procqc.graph import draft

# Markers of an example, and words earlier prompt versions used as example items (from several domains).
EXAMPLE_MARKERS = r"\be\.g\.|\bi\.e\.,? (?:a|an|the)\b|such as|for example|for instance|\blike a\b"
EXAMPLE_WORDS = [
    "screwdriver", "coin", "phillips", "allen", "hex key", "nitrile", "latex", "glove", "beaker", "flask", "ramekin",
    "microwave", "salsa", "garlic", "toothpick", "sandwich", "lettuce", "pepper", "salt", "spoon", "scoop", "pipette",
    "jar", "drawer", "fridge", "tablet", "phone", "towel", "knife", "cutting board", "book", "lid", "cord", "egg",
    "shoe", "sneaker", "rack", "shelf", "laundry", "muffin", "cheese", "spinach", "tomato", "puree", "mustard",
    "cumin", "chili", "oil", "pan", "blender", "tuna", "bowl", "mug", "onion", "butter", "bread", "whisk", "sieve",
    "spatula", "plate", "kettle", "sugar", "fork", "cup", "bolt", "nut", "sandpaper", "tray", "vial", "dish",
]


def _texts():
    return [(name, p.text) for name, p in prompts.PROMPTS.items()]


@pytest.mark.parametrize("name,text", _texts())
def test_no_example_markers(name, text):
    m = re.search(EXAMPLE_MARKERS, text, re.I)
    assert not m, (name, text[max(0, m.start() - 60):m.end() + 60])


@pytest.mark.parametrize("name,text", _texts())
def test_no_example_items(name, text):
    hits = [w for w in EXAMPLE_WORDS if re.search(rf"\b{re.escape(w)}(?:e?s)?\b", text, re.I)]
    assert not hits, (name, hits)


def test_registry_lookup():
    for name, p in prompts.PROMPTS.items():
        assert p.name == name and p.version and p.text.strip() and p.used_by
        assert prompts.get(name) == p.text
    with pytest.raises(KeyError):
        prompts.get("no.such.prompt")


def test_every_caller_name_resolves():
    """Every prompts.get("...") in the package names a registered prompt."""
    from pathlib import Path
    root = Path(prompts.__file__).parent
    names = {m for f in root.rglob("*.py") for m in re.findall(r'prompts\.get\("([^"]+)"\)', f.read_text())}
    assert names and names <= set(prompts.PROMPTS), names - set(prompts.PROMPTS)
    assert set(prompts.PROMPTS) <= names, set(prompts.PROMPTS) - names  # no unused prompt


def test_checker_keys_match_drafter():
    assert [k.strip() for k in prompts.CHECKERS.split(",")] == list(draft.CHECKER_KEYS)
