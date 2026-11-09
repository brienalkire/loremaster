import json
import random
from collections import Counter

import pytest

import dice


@pytest.fixture
def seeded(monkeypatch):
    monkeypatch.setattr(dice, "_rng", random.Random(1234))


@pytest.mark.parametrize("notation, parsed", [
    ("1d20", (1, 20, 0)),
    ("d20", (1, 20, 0)),
    ("3d6", (3, 6, 0)),
    ("2D6+3", (2, 6, 3)),
    (" 1d8 - 1 ", (1, 8, -1)),
])
def test_parse(notation, parsed):
    assert dice.parse(notation) == parsed


@pytest.mark.parametrize("notation", ["", "20", "1d", "1d1", "0d6", "101d6", "1d1001", "1d6+1001", "d20 for Bob"])
def test_parse_rejects(notation):
    with pytest.raises(ValueError):
        dice.parse(notation)


def test_uses_the_system_random_source():
    assert isinstance(dice.secrets.SystemRandom(), type(dice._rng))


def test_results_are_in_range_and_cover_every_face():
    seen = Counter()
    for _ in range(2000):
        result = dice.roll_one("1d20")["results"]
        assert len(result) == 1 and 1 <= result[0] <= 20
        seen[result[0]] += 1
    assert set(seen) == set(range(1, 21))


def test_several_dice_and_modifier(seeded):
    r = dice.roll_one("3d6+2")
    assert r["dice"] == "3d6+2" and len(r["results"]) == 3
    assert all(1 <= n <= 6 for n in r["results"])
    assert r["total"] == sum(r["results"]) + 2 and r["modifier"] == 2


def test_labelled_rolls_report_highest_and_lowest(monkeypatch):
    values = iter([16, 5, 12])
    monkeypatch.setattr(dice, "_rng", type("R", (), {"randint": lambda self, a, b: next(values)})())
    out = dice.roll([{"dice": "1d20", "label": "drwargame"}, {"dice": "1d20", "label": "nuke"},
                     {"dice": "1d20", "label": "Jayne"}])
    assert [(r["label"], r["total"]) for r in out["rolls"]] == [("drwargame", 16), ("nuke", 5), ("Jayne", 12)]
    assert out["highest"] == {"total": 16, "labels": ["drwargame"]}
    assert out["lowest"] == {"total": 5, "labels": ["nuke"]}


def test_ties_list_every_label(monkeypatch):
    values = iter([9, 9, 3])
    monkeypatch.setattr(dice, "_rng", type("R", (), {"randint": lambda self, a, b: next(values)})())
    out = dice.roll([{"dice": "d20", "label": "A"}, {"dice": "d20", "label": "B"}, {"dice": "d20", "label": "C"}])
    assert out["highest"]["labels"] == ["A", "B"]


def test_unlabelled_roll_has_no_ranking(seeded):
    out = dice.roll([{"dice": "3d6"}])
    assert "highest" not in out and "label" not in out["rolls"][0]


def test_errors_are_returned_not_raised():
    assert "error" in dice.roll([])
    assert "error" in dice.roll([{"dice": "banana"}])
    assert "error" in dice.roll([{"dice": "d6"}] * (dice.MAX_ROLLS_PER_CALL + 1))


def test_execute_tool(seeded):
    out = json.loads(dice.execute_tool("roll_dice", {"rolls": [{"dice": "2d6"}]}))
    assert len(out["rolls"][0]["results"]) == 2
    assert "error" in json.loads(dice.execute_tool("roll_dice", {"rolls": "2d6"}))
    assert "error" in json.loads(dice.execute_tool("other", {}))
