"""Live Steam store-data lookup, exposed to Claude as a tool.

Uses Steam's public storefront endpoints (search + appdetails) and the
public ISteamUserStats current-player-count endpoint. None of these
require a Steam Web API key - that's only needed for user-specific data
(owned games, achievements), which is explicitly out of scope for this
first pass; see voxport/loremaster design notes for that follow-on.
"""

import json

import requests

STEAM_SEARCH_URL = "https://store.steampowered.com/api/storesearch/"
STEAM_APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
STEAM_PLAYERCOUNT_URL = "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"

# Don't let a slow/hanging Steam endpoint stall a Discord reply indefinitely.
REQUEST_TIMEOUT = 8

# Filters appdetails' `categories` down to the ones relevant to "will this
# work for our group" decisions - Steam Achievements, Trading Cards, Steam
# Cloud, etc. aren't useful here.
RELEVANT_CATEGORIES = {
    "Multi-player", "Co-op", "Online Co-op", "LAN Co-op",
    "Shared/Split Screen Co-op", "PvP", "Online PvP",
    "Shared/Split Screen PvP", "Cross-Platform Multiplayer",
    "Full controller support", "Partial Controller Support",
    "Remote Play Together",
}

STEAM_TOOLS = [
    {
        "name": "lookup_steam_game",
        "description": (
            "Look up live Steam store data for a game by name: genres, "
            "multiplayer/co-op support, current price and sale status, "
            "release date, Early Access status, and current active player "
            "count. Use this when you need something your training data "
            "can't reliably tell you - anything released or updated "
            "recently, current pricing/sales, or whether a game's "
            "multiplayer scene is still active. Don't use it for "
            "well-established facts you already know confidently - it "
            "adds real latency to the reply, so reach for it only when it "
            "actually changes the answer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "game_name": {
                    "type": "string",
                    "description": "The game's common name, e.g. 'Baldur's Gate 3'.",
                }
            },
            "required": ["game_name"],
        },
    }
]

# Alias used by main.py's generic tool registry (see TOOL_MODULES).
TOOLS = STEAM_TOOLS


def search_steam_apps(query: str, limit: int = 5) -> list[dict]:
    """Return up to `limit` {appid, name} candidates matching `query`."""
    resp = requests.get(
        STEAM_SEARCH_URL,
        params={"term": query, "cc": "us", "l": "en"},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    items = resp.json().get("items", [])
    return [{"appid": item["id"], "name": item["name"]} for item in items[:limit]]


def get_app_details(appid: int) -> dict | None:
    """Return a filtered summary of Steam store data for `appid`, or None
    if Steam has no successful store page data for it (delisted, region-
    restricted, etc.)."""
    resp = requests.get(
        STEAM_APPDETAILS_URL,
        params={"appids": appid, "cc": "us", "l": "en"},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    payload = resp.json().get(str(appid))
    if not payload or not payload.get("success"):
        return None
    data = payload["data"]

    genres = [g["description"] for g in data.get("genres", [])]
    categories = [
        c["description"] for c in data.get("categories", [])
        if c["description"] in RELEVANT_CATEGORIES
    ]

    price = "Free to play" if data.get("is_free") else None
    if not price and "price_overview" in data:
        po = data["price_overview"]
        price = po["final_formatted"]
        if po.get("discount_percent"):
            price += f" ({po['discount_percent']}% off, was {po['initial_formatted']})"

    return {
        "name": data.get("name"),
        "appid": appid,
        "genres": genres,
        "multiplayer_categories": categories,
        "price": price,
        "release_date": data.get("release_date", {}).get("date"),
        "is_early_access": "Early Access" in genres,
        "metacritic_score": data.get("metacritic", {}).get("score"),
        "short_description": data.get("short_description"),
    }


def get_current_players(appid: int) -> int | None:
    """Return the current active player count for `appid`, or None if the
    lookup fails - this is best-effort, not worth failing the whole tool
    call over."""
    try:
        resp = requests.get(
            STEAM_PLAYERCOUNT_URL,
            params={"appid": appid},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        result = resp.json().get("response", {})
        if result.get("result") == 1:
            return result.get("player_count")
    except requests.RequestException:
        pass
    return None


def lookup_steam_game(game_name: str) -> dict:
    """Search Steam for `game_name` and return details for the best match,
    plus a short list of alternates in case the match was wrong. Never
    raises - a flaky third-party API shouldn't crash the tool loop.
    """
    try:
        candidates = search_steam_apps(game_name)
        if not candidates:
            return {"error": f"No Steam store results found for '{game_name}'."}

        top = candidates[0]
        details = get_app_details(top["appid"])
        if details is None:
            return {
                "error": (
                    f"Found '{top['name']}' on Steam but couldn't fetch its "
                    "store details."
                ),
                "other_matches": candidates[1:4],
            }

        details["current_players"] = get_current_players(top["appid"])
        alternates = [c for c in candidates[1:4] if c["name"] != details["name"]]
        if alternates:
            details["other_matches"] = alternates
        return details
    except Exception as exc:  # noqa: BLE001 - a Steam hiccup shouldn't break the reply
        return {"error": f"Steam lookup failed: {exc}"}


def execute_tool(name: str, tool_input: dict) -> str:
    """Dispatch a tool_use block by name; return its tool_result content
    as a JSON string."""
    if name == "lookup_steam_game":
        result = lookup_steam_game(tool_input.get("game_name", ""))
    else:
        result = {"error": f"Unknown tool: {name}"}
    return json.dumps(result)
