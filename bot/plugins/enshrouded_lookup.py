"""Static Enshrouded game-data lookup (items, crafting/cooking/upgrade
recipes) via the community-run Shrouded Tools database
(https://shrouded.tools/en/api/), exposed to Claude as tools.

Unlike steam_lookup.py's genuinely live data (price, player count), this
is a fixed per-game-version dataset - fetched once from the static JSON
dumps and cached in memory for the life of the process, not re-fetched
per query. (The live /api/v1/items search endpoint returned an empty list
for every query tried during development - the static dumps are what
actually work; revisit if that changes.) Cache lives until the bot
restarts, which is an acceptable refresh cadence for this dev workflow -
if Enshrouded's still-pre-release patches start meaningfully outdating a
long-running process, add a TTL here.

AGPL-3.0-licensed community data - credit shrouded.tools when citing it.
"""

import json

import requests

ITEMS_DUMP_URL = "https://shrouded.tools/assets/wiki/items.json"
RECIPES_DUMP_URL = "https://shrouded.tools/assets/wiki/recipes.json"

REQUEST_TIMEOUT = 15

_items_cache: list[dict] | None = None
_recipes_cache: list[dict] | None = None


def _load_items() -> list[dict]:
    global _items_cache
    if _items_cache is None:
        resp = requests.get(ITEMS_DUMP_URL, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        _items_cache = resp.json()["items"]
    return _items_cache


def _load_recipes() -> list[dict]:
    global _recipes_cache
    if _recipes_cache is None:
        resp = requests.get(RECIPES_DUMP_URL, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        _recipes_cache = resp.json()["recipes"]
    return _recipes_cache


def _matches(text: str | None, query: str) -> bool:
    return bool(text) and query.lower() in text.lower()


def summarize_item(item: dict) -> dict:
    summary = {
        "name": item.get("name_en"),
        "category": item.get("category"),
        "rarity": item.get("rarity"),
        "equip_slot": item.get("equip_slot"),
        "level_range": item.get("level_range"),
        "description": item.get("desc_en"),
    }
    if item.get("lore_en"):
        summary["lore"] = item["lore_en"]
    if item.get("acquisition_hint_en"):
        summary["acquisition_hint"] = item["acquisition_hint_en"]
    if item.get("damage_total") is not None:
        summary["damage_total"] = item["damage_total"]
        summary["damage_distribution"] = item.get("damage_distribution")
        summary["weapon_type"] = item.get("weapon_category_type")
        summary["weapon_class"] = item.get("weapon_class_type")
    if item.get("armor_total") is not None:
        summary["armor_total"] = item["armor_total"]
        summary["armor_distribution"] = item.get("armor_distribution")
    return summary


def summarize_recipe(recipe: dict) -> dict:
    return {
        "produces": [o.get("name") for o in recipe.get("output", [])],
        "output": recipe.get("output"),
        "input": recipe.get("input"),
        "level": recipe.get("level"),
        "is_cooking": recipe.get("is_cooking"),
        "is_upgrade": recipe.get("is_upgrade"),
        "requires_sheltered": recipe.get("requires_sheltered"),
        "duration_s": recipe.get("duration_s"),
    }


def lookup_enshrouded_item(query: str, category: str | None = None, limit: int = 5) -> dict:
    try:
        items = _load_items()
    except Exception as exc:  # noqa: BLE001 - a fetch hiccup shouldn't break the reply
        return {"error": f"Enshrouded item lookup failed: {exc}"}

    matches = [
        item for item in items
        if _matches(item.get("name_en"), query)
        and (category is None or (item.get("category") or "").lower() == category.lower())
    ]
    if not matches:
        suffix = f" in category '{category}'" if category else ""
        return {"error": f"No Enshrouded items found matching '{query}'{suffix}."}
    return {"matches": [summarize_item(item) for item in matches[:limit]], "total_matches": len(matches)}


def lookup_enshrouded_recipe(query: str, limit: int = 5) -> dict:
    try:
        recipes = _load_recipes()
    except Exception as exc:  # noqa: BLE001 - a fetch hiccup shouldn't break the reply
        return {"error": f"Enshrouded recipe lookup failed: {exc}"}

    matches = [r for r in recipes if any(_matches(o.get("name"), query) for o in r.get("output", []))]
    if not matches:
        return {"error": f"No Enshrouded recipes found producing '{query}'."}
    return {"matches": [summarize_recipe(r) for r in matches[:limit]], "total_matches": len(matches)}


ENSHROUDED_TOOLS = [
    {
        "name": "lookup_enshrouded_item",
        "description": (
            "Look up Enshrouded item data by name: category, rarity, level "
            "requirement, weapon damage or armor stats, and description. "
            "Data comes from the community-run Shrouded Tools database "
            "(shrouded.tools) - static per-game-version data (item stats), "
            "not live session state. Use for factual questions about what "
            "an item does or requires. Don't use this for the party's own "
            "current inventory or gear loadout - that's tracked in "
            "campaign memory (get_campaign_state), not this database."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Item name or partial name to search for, e.g. 'iron sword'."},
                "category": {"type": "string", "description": "Optional exact category filter, e.g. 'Weapons', 'Equipment', 'Materials'."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "lookup_enshrouded_recipe",
        "description": (
            "Look up an Enshrouded crafting/cooking/upgrade recipe by the "
            "name of the item it produces: required inputs, level "
            "requirement, and whether it needs shelter. Same static "
            "community database as lookup_enshrouded_item."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Name (or partial name) of the item the recipe produces, e.g. 'iron sword'."},
            },
            "required": ["query"],
        },
    },
]

# Alias used by main.py's generic tool registry (see TOOL_MODULES).
TOOLS = ENSHROUDED_TOOLS

# Added to the system prompt while this plugin is active.
INSTRUCTIONS = """## Enshrouded Item & Recipe Data

`lookup_enshrouded_item` and `lookup_enshrouded_recipe` query the
community-run Shrouded Tools database (shrouded.tools) for factual, static
Enshrouded game data: item stats (rarity, level, weapon damage or armor
values) and crafting, cooking and upgrade recipes (inputs, level, whether
shelter is required). Use these instead of memory when a player asks
something specific and checkable, such as "what's the X sword's damage" or
"what do I need to craft Y". If you quote a specific number from these
tools, mention in passing that it came from Shrouded Tools (the data is
community-licensed and asks for that credit). There's no need to add that
to every reply.

Don't confuse this with the party's own state. The party's inventory,
equipped gear and build choices live in campaign memory
(`get_campaign_state`), not in this database. This tool says what an item
or recipe *is*; campaign memory says what the party *has*."""


def execute_tool(name: str, tool_input: dict) -> str:
    """Dispatch a tool_use block by name; return its tool_result content as
    a JSON string. Never raises - a fetch/parse hiccup shouldn't crash the
    tool loop."""
    try:
        if name == "lookup_enshrouded_item":
            result = lookup_enshrouded_item(tool_input.get("query", ""), tool_input.get("category"))
        elif name == "lookup_enshrouded_recipe":
            result = lookup_enshrouded_recipe(tool_input.get("query", ""))
        else:
            result = {"error": f"Unknown tool: {name}"}
    except Exception as exc:  # noqa: BLE001 - never let a lookup break the reply
        result = {"error": f"Enshrouded lookup error: {exc}"}
    return json.dumps(result)
