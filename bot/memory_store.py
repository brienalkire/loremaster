"""SQLite-backed persistent memory for loremaster.

Two tiers: per-campaign memory (a running "current state" doc plus a short
append-only event log) and cross-campaign general memory. Exactly one
campaign is active at a time, tracked in bot_state — switching is meant to
happen live via the tools below instead of editing GAME_EXTENSION and
restarting.

Exposed to Claude as tools, same pattern as steam_lookup.py: a *_TOOLS list
plus execute_tool(name, input) for main.py's tool-dispatch loop to call.
"""

import json
import sqlite3
from datetime import datetime, timezone
import paths

DB_PATH = paths.DB_PATH
INSTRUCTIONS_DIR = paths.INSTRUCTIONS_DIR


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist yet. Safe to call on every startup."""
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS campaigns (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                game TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_active_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS bot_state (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS campaign_state (
                campaign_id INTEGER PRIMARY KEY REFERENCES campaigns(id),
                notes TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS campaign_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL REFERENCES campaigns(id),
                entry TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS general_memory (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                notes TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );
        """)
        conn.execute(
            "INSERT OR IGNORE INTO general_memory (id, notes, updated_at) VALUES (1, '', ?)",
            (_now(),),
        )


# ---------------------------------------------------------------------------
# Campaign management
# ---------------------------------------------------------------------------

def get_active_campaign() -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute(
            "SELECT c.* FROM campaigns c "
            "JOIN bot_state s ON s.key = 'active_campaign_id' AND s.value = CAST(c.id AS TEXT)"
        ).fetchone()


def list_campaigns() -> dict:
    active = get_active_campaign()
    active_id = active["id"] if active else None
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, name, game, last_active_at FROM campaigns ORDER BY last_active_at DESC"
        ).fetchall()
    return {
        "campaigns": [
            {
                "name": r["name"],
                "game": r["game"],
                "last_active_at": r["last_active_at"],
                "active": r["id"] == active_id,
            }
            for r in rows
        ]
    }


def create_campaign(name: str, game: str) -> dict:
    if not (INSTRUCTIONS_DIR / game).is_dir():
        available = sorted(p.name for p in INSTRUCTIONS_DIR.iterdir() if p.is_dir())
        return {"error": f"No instructions found for game '{game}'. Available games: {available}"}
    now = _now()
    with _connect() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO campaigns (name, game, created_at, last_active_at) VALUES (?, ?, ?, ?)",
                (name, game, now, now),
            )
        except sqlite3.IntegrityError:
            return {"error": f"A campaign named '{name}' already exists."}
        campaign_id = cur.lastrowid
        conn.execute(
            "INSERT INTO campaign_state (campaign_id, notes, updated_at) VALUES (?, '', ?)",
            (campaign_id, now),
        )
        conn.execute(
            "INSERT INTO bot_state (key, value) VALUES ('active_campaign_id', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(campaign_id),),
        )
    return {"created": name, "game": game, "active": True}


def switch_campaign(name: str) -> dict:
    with _connect() as conn:
        row = conn.execute("SELECT id, game FROM campaigns WHERE name = ?", (name,)).fetchone()
        if row is None:
            return {"error": f"No campaign named '{name}'. Use list_campaigns to see what's tracked."}
        conn.execute(
            "INSERT INTO bot_state (key, value) VALUES ('active_campaign_id', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(row["id"]),),
        )
        conn.execute("UPDATE campaigns SET last_active_at = ? WHERE id = ?", (_now(), row["id"]))
    return {"switched_to": name, "game": row["game"]}


# ---------------------------------------------------------------------------
# Campaign state / log (read-before-write: callers should fetch current
# state, edit it, then write the full replacement back — not a diff).
# ---------------------------------------------------------------------------

def get_campaign_state() -> dict:
    active = get_active_campaign()
    if active is None:
        return {"error": "No active campaign. Use list_campaigns or create_campaign first."}
    with _connect() as conn:
        row = conn.execute(
            "SELECT notes FROM campaign_state WHERE campaign_id = ?", (active["id"],)
        ).fetchone()
    return {"campaign": active["name"], "notes": row["notes"] if row else ""}


# If a rewrite comes in shorter than this fraction of the current notes,
# treat it as likely accidental data loss (e.g. a lazy "[...unchanged...]"
# placeholder instead of the real prior content) rather than a deliberate
# edit, and require an explicit confirm_shrink=true to accept it. Caught a
# real incident live: Claude elided the prior character-sheet content
# instead of re-pasting it verbatim, silently destroying it.
SHRINK_GUARD_RATIO = 0.5


def _shrink_guard(current: str, new: str, confirm_shrink: bool) -> dict | None:
    if current and len(new) < len(current) * SHRINK_GUARD_RATIO and not confirm_shrink:
        return {
            "error": (
                f"New notes ({len(new)} chars) are less than half the length of "
                f"the current notes ({len(current)} chars). This usually means "
                "content got dropped rather than intentionally removed - did you "
                "paste back the full current text VERBATIM (no '[unchanged]' or "
                "'[...]' placeholders - those are not preserved, they replace "
                "the real content) before editing it? If this shrink is genuinely "
                "intentional, call again with confirm_shrink=true."
            )
        }
    return None


def update_campaign_state(notes: str, confirm_shrink: bool = False) -> dict:
    active = get_active_campaign()
    if active is None:
        return {"error": "No active campaign. Use list_campaigns or create_campaign first."}
    with _connect() as conn:
        current_row = conn.execute(
            "SELECT notes FROM campaign_state WHERE campaign_id = ?", (active["id"],)
        ).fetchone()
        current_notes = current_row["notes"] if current_row else ""
        guard_error = _shrink_guard(current_notes, notes, confirm_shrink)
        if guard_error:
            return guard_error
        conn.execute(
            "INSERT INTO campaign_state (campaign_id, notes, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(campaign_id) DO UPDATE SET notes = excluded.notes, updated_at = excluded.updated_at",
            (active["id"], notes, _now()),
        )
    return {"updated": active["name"]}


def log_campaign_event(entry: str) -> dict:
    active = get_active_campaign()
    if active is None:
        return {"error": "No active campaign. Use list_campaigns or create_campaign first."}
    with _connect() as conn:
        conn.execute(
            "INSERT INTO campaign_log (campaign_id, entry, created_at) VALUES (?, ?, ?)",
            (active["id"], entry, _now()),
        )
    return {"logged": entry}


# ---------------------------------------------------------------------------
# General (cross-campaign) memory
# ---------------------------------------------------------------------------

def get_general_memory() -> dict:
    with _connect() as conn:
        row = conn.execute("SELECT notes FROM general_memory WHERE id = 1").fetchone()
    return {"notes": row["notes"] if row else ""}


def remember_general(notes: str, confirm_shrink: bool = False) -> dict:
    with _connect() as conn:
        current_row = conn.execute("SELECT notes FROM general_memory WHERE id = 1").fetchone()
        current_notes = current_row["notes"] if current_row else ""
        guard_error = _shrink_guard(current_notes, notes, confirm_shrink)
        if guard_error:
            return guard_error
        conn.execute(
            "UPDATE general_memory SET notes = ?, updated_at = ? WHERE id = 1",
            (notes, _now()),
        )
    return {"updated": True}


# ---------------------------------------------------------------------------
# System-prompt integration (called by main.py's build_system_prompt())
# ---------------------------------------------------------------------------

def active_campaign_context() -> tuple[str | None, str]:
    """Return (game, prompt_text) for the active campaign, or (None, "") if
    no campaign is active yet — callers should fall back to GAME_EXTENSION
    with no campaign memory appended in that case."""
    active = get_active_campaign()
    if active is None:
        return None, ""
    with _connect() as conn:
        state_row = conn.execute(
            "SELECT notes FROM campaign_state WHERE campaign_id = ?", (active["id"],)
        ).fetchone()
        log_rows = conn.execute(
            "SELECT entry, created_at FROM campaign_log WHERE campaign_id = ? "
            "ORDER BY id DESC LIMIT 20",
            (active["id"],),
        ).fetchall()

    parts = [f"## Active campaign: {active['name']}"]
    if state_row and state_row["notes"]:
        parts.append(f"### Current state\n{state_row['notes']}")
    if log_rows:
        log_text = "\n".join(f"- ({r['created_at']}) {r['entry']}" for r in reversed(log_rows))
        parts.append(f"### Recent events\n{log_text}")
    return active["game"], "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Claude tool definitions + dispatch
# ---------------------------------------------------------------------------

MEMORY_TOOLS = [
    {
        "name": "list_campaigns",
        "description": (
            "List every campaign being tracked (name, game, which one is "
            "currently active). Use when the group asks what campaigns "
            "exist, wants to switch, or seems unsure what's being tracked."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "create_campaign",
        "description": (
            "Create a new campaign and make it active immediately. `game` "
            "must match an existing game extension folder (check "
            "list_campaigns for examples, or ask the group if unsure which "
            "games are available) — adding support for a brand-new game "
            "isn't something this tool can do. Only call this after "
            "confirming the name and game with the group, since it switches "
            "context right away."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "A short, human-chosen campaign name, e.g. 'bg3-solo' or 'nms-weekly'."},
                "game": {"type": "string", "description": "The game extension folder name, e.g. 'enshrouded'."},
            },
            "required": ["name", "game"],
        },
    },
    {
        "name": "switch_campaign",
        "description": "Switch the active campaign to an existing one by name. Use when the group says they're playing a different campaign than what's currently active.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "get_campaign_state",
        "description": "Fetch the active campaign's current saved state (party/character status, objective, notable inventory, etc.) verbatim. Always call this before update_campaign_state so the rewrite is based on the real current text, not a guess.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "update_campaign_state",
        "description": (
            "Overwrite the active campaign's saved state with a fresh, "
            "complete write-up. Pass the FULL updated notes, not just what "
            "changed — this replaces the previous notes entirely and is NOT "
            "a diff. Fetch the current notes with get_campaign_state first, "
            "then write back the ENTIRE text with your edit folded in — "
            "copy unchanged sections VERBATIM, character by character. "
            "NEVER write a placeholder like '[...unchanged...]' or "
            "'[rest of character sheets retained]' in place of real content "
            "— that placeholder text is exactly what gets stored, and "
            "whatever it stands in for is permanently gone. If your rewrite "
            "comes out much shorter than the current notes, you'll get an "
            "error asking you to confirm that's intentional — that's a "
            "safety check, not a bug; don't just resubmit with "
            "confirm_shrink=true without checking you didn't accidentally "
            "drop something. Use this tool when something state-worthy "
            "happens: leveling up, a major acquisition, a new objective."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "notes": {"type": "string"},
                "confirm_shrink": {
                    "type": "boolean",
                    "description": "Only set true after checking a much-shorter rewrite is a deliberate removal, not accidental data loss.",
                },
            },
            "required": ["notes"],
        },
    },
    {
        "name": "log_campaign_event",
        "description": "Append one short, timestamped note to the active campaign's event log (a running history, separate from the current-state summary) — for memorable one-off moments (a big decision, a death, a twist), not routine chatter.",
        "input_schema": {
            "type": "object",
            "properties": {"entry": {"type": "string"}},
            "required": ["entry"],
        },
    },
    {
        "name": "get_general_memory",
        "description": "Fetch the cross-campaign general memory (group preferences, running jokes, facts not tied to a specific campaign) verbatim. Call before remember_general so the rewrite is based on the real current text.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "remember_general",
        "description": (
            "Overwrite the cross-campaign general memory with a fresh, "
            "complete write-up — NOT a diff. Fetch with get_general_memory "
            "first, then write back the ENTIRE text with unchanged sections "
            "copied VERBATIM. Never write a placeholder like "
            "'[unchanged]' in place of real content; that's what gets "
            "stored, permanently losing whatever it stood in for. A much- "
            "shorter rewrite triggers a confirm_shrink safety check."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "notes": {"type": "string"},
                "confirm_shrink": {
                    "type": "boolean",
                    "description": "Only set true after checking a much-shorter rewrite is a deliberate removal, not accidental data loss.",
                },
            },
            "required": ["notes"],
        },
    },
]

# Alias used by main.py's generic tool registry (see TOOL_MODULES).
TOOLS = MEMORY_TOOLS


def execute_tool(name: str, tool_input: dict) -> str:
    """Dispatch a tool_use block by name; return its tool_result content as
    a JSON string. Never raises - a DB hiccup shouldn't crash the tool loop."""
    try:
        if name == "list_campaigns":
            result = list_campaigns()
        elif name == "create_campaign":
            result = create_campaign(tool_input.get("name", ""), tool_input.get("game", ""))
        elif name == "switch_campaign":
            result = switch_campaign(tool_input.get("name", ""))
        elif name == "get_campaign_state":
            result = get_campaign_state()
        elif name == "update_campaign_state":
            result = update_campaign_state(
                tool_input.get("notes", ""), tool_input.get("confirm_shrink", False)
            )
        elif name == "log_campaign_event":
            result = log_campaign_event(tool_input.get("entry", ""))
        elif name == "get_general_memory":
            result = get_general_memory()
        elif name == "remember_general":
            result = remember_general(
                tool_input.get("notes", ""), tool_input.get("confirm_shrink", False)
            )
        else:
            result = {"error": f"Unknown tool: {name}"}
    except Exception as exc:  # noqa: BLE001 - a DB hiccup shouldn't break the reply
        result = {"error": f"Memory store error: {exc}"}
    return json.dumps(result)
