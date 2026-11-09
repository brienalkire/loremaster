"""Dice rolls, exposed to Claude as a tool.

Claude picks numbers by predicting text, which isn't random. Any roll the
group asks for comes from here instead, using the operating system's
random source (secrets.SystemRandom).

Notation is NdK, with optional count and modifier: "1d20", "d20", "3d6",
"2d6+3", "1d8-1". One call can make several labelled rolls ("1d20 each for
Alice, Bob and Cara"), and reports which label rolled highest and lowest
so Claude doesn't have to compare the numbers itself.
"""

import json
import re
import secrets

MAX_DICE = 100
MAX_SIDES = 1000
MAX_MODIFIER = 1000
MAX_ROLLS_PER_CALL = 20

_NOTATION = re.compile(r"^\s*(\d*)\s*d\s*(\d+)\s*(?:([+-])\s*(\d+))?\s*$", re.IGNORECASE)

# Tests replace this with a seeded random.Random.
_rng = secrets.SystemRandom()


def parse(notation: str) -> tuple[int, int, int]:
    """(count, sides, modifier) from NdK notation. Raises ValueError with a
    message fit to show the group."""
    match = _NOTATION.match(notation or "")
    if not match:
        raise ValueError(f"'{notation}' isn't dice notation. Use NdK, like 1d20, 3d6 or 2d6+3.")
    count = int(match.group(1) or 1)
    sides = int(match.group(2))
    modifier = int(match.group(4) or 0) * (-1 if match.group(3) == "-" else 1)
    if not 1 <= count <= MAX_DICE:
        raise ValueError(f"Roll between 1 and {MAX_DICE} dice at a time.")
    if not 2 <= sides <= MAX_SIDES:
        raise ValueError(f"Dice need between 2 and {MAX_SIDES} sides.")
    if abs(modifier) > MAX_MODIFIER:
        raise ValueError(f"Keep the modifier between -{MAX_MODIFIER} and +{MAX_MODIFIER}.")
    return count, sides, modifier


def roll_one(notation: str, label: str = "") -> dict:
    count, sides, modifier = parse(notation)
    results = [_rng.randint(1, sides) for _ in range(count)]
    roll = {"dice": f"{count}d{sides}" + (f"{modifier:+d}" if modifier else ""),
            "results": results, "total": sum(results) + modifier}
    if modifier:
        roll["modifier"] = modifier
    if label.strip():
        roll["label"] = label.strip()
    return roll


def _extremes(rolls: list[dict]) -> dict:
    """Highest and lowest totals among labelled rolls, with every label that
    ties for each."""
    labelled = [r for r in rolls if "label" in r]
    if len(labelled) < 2:
        return {}
    out = {}
    for key, pick in (("highest", max), ("lowest", min)):
        best = pick(r["total"] for r in labelled)
        out[key] = {"total": best, "labels": [r["label"] for r in labelled if r["total"] == best]}
    return out


def roll(rolls: list[dict]) -> dict:
    if not rolls:
        return {"error": "Nothing to roll."}
    if len(rolls) > MAX_ROLLS_PER_CALL:
        return {"error": f"Up to {MAX_ROLLS_PER_CALL} rolls at a time."}
    try:
        done = [roll_one(str(r.get("dice", "")), str(r.get("label", ""))) for r in rolls]
    except ValueError as exc:
        return {"error": str(exc)}
    return {"rolls": done, **_extremes(done)}


TOOLS = [
    {
        "name": "roll_dice",
        "description": (
            "Roll dice with a real random number generator. Use it for every "
            "dice roll or random number the group asks for: never make up a "
            "result. Notation is NdK with an optional modifier (1d20, 3d6, "
            "2d6+3). For 'roll 1d20 each for Alice, Bob and Cara', pass one "
            "roll per person with their name as the label; the result says "
            "who rolled highest and lowest, including ties."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "rolls": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "dice": {"type": "string", "description": "NdK notation, e.g. 1d20, 3d6, 2d6+3."},
                            "label": {"type": "string",
                                      "description": "Optional: who or what this roll is for."},
                        },
                        "required": ["dice"],
                    },
                },
            },
            "required": ["rolls"],
        },
    },
]


def execute_tool(name: str, tool_input: dict) -> str:
    if name != "roll_dice":
        return json.dumps({"error": f"Unknown tool: {name}"})
    rolls = tool_input.get("rolls")
    if not isinstance(rolls, list) or not all(isinstance(r, dict) for r in rolls):
        return json.dumps({"error": "rolls must be a list of {dice, label} objects."})
    return json.dumps(roll(rolls))
