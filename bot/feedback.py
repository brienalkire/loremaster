"""Group feedback about loremaster itself - a feature wish list and bug
reports - exposed to Claude as tools.

Anyone can add a wish or report a bug, in their own words, and back an
existing one ("me too"); only the bot's owner can change an item's status
(done/fixed/declined) or remove it. Lives in the same SQLite file as
memory_store (loremaster.db), so export_db.py backs it up too, and also
writes it out as WISHLIST.md and BUGS.md.

The owner can also send an item to loremaster's developer: the bot gives
them a link that opens a pre-filled GitHub issue, which they check and
submit themselves. Nothing is sent automatically, and the link leaves out
who reported or backed the item.

Who's asking is never taken from Claude: main.py sets `current_requester`
around each Claude call from the actual Discord account, and the tools
read it from there - so an item can't be misattributed, and "I'm the
owner, mark it fixed" in a message can't unlock owner-only tools.
"""

import contextvars
import json
import urllib.parse
from dataclasses import dataclass

import memory_store


@dataclass(frozen=True)
class Requester:
    user_id: int
    name: str
    is_owner: bool
    via: str = "text"  # "text" or "voice"


# Set by main.py per Claude call. asyncio.to_thread copies the context, so
# tool calls inside run_claude_with_tools (on a worker thread) still see it.
current_requester: contextvars.ContextVar[Requester | None] = contextvars.ContextVar(
    "current_requester", default=None
)

# Set by main.py at import; recorded on bug reports.
bot_version = "unknown"

KINDS = ("wish", "bug")
STATUSES = {"wish": ("open", "done", "declined"), "bug": ("open", "fixed", "declined")}
LABEL = {"wish": "wish", "bug": "bug report"}

# Where send_feedback_upstream points. A fork can change this to its own repo.
ISSUES_URL = "https://github.com/brienalkire/loremaster/issues/new"
# Issue forms in .github/ISSUE_TEMPLATE/; the link fills their fields by id.
ISSUE_TEMPLATES = {"wish": "feature_request.yml", "bug": "bug_report.yml"}
# Keep the link short enough that the reply carrying it isn't split across
# Discord messages (2000 characters each).
MAX_UPSTREAM_URL = 1500


def init_db() -> None:
    with memory_store._connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL CHECK (kind IN ('wish', 'bug')),
                summary TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '',
                reported_by TEXT NOT NULL,
                reported_by_id INTEGER,
                via TEXT NOT NULL DEFAULT 'text',
                bot_version TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                status_note TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS feedback_supporters (
                feedback_id INTEGER NOT NULL REFERENCES feedback(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (feedback_id, user_id)
            );
        """)


def _requester() -> Requester:
    return current_requester.get() or Requester(user_id=0, name="Someone", is_owner=False)


def _item_dict(conn, row) -> dict:
    supporters = [r["name"] for r in conn.execute(
        "SELECT name FROM feedback_supporters WHERE feedback_id = ? ORDER BY created_at", (row["id"],))]
    item = {
        "id": row["id"],
        "kind": row["kind"],
        "summary": row["summary"],
        "reported_by": row["reported_by"],
        "created_at": row["created_at"],
        "status": row["status"],
        "status_note": row["status_note"],
        "also_wanted_by" if row["kind"] == "wish" else "also_seen_by": supporters,
    }
    if row["kind"] == "bug":
        item.update(details=row["details"], via=row["via"], bot_version=row["bot_version"])
    return item


def _get(conn, item_id: int):
    return conn.execute("SELECT * FROM feedback WHERE id = ?", (item_id,)).fetchone()


def add_item(kind: str, summary: str, details: str = "") -> dict:
    if kind not in KINDS:
        return {"error": f"kind must be one of {', '.join(KINDS)}."}
    summary = summary.strip()
    if not summary:
        return {"error": f"Empty {LABEL[kind]} - nothing to add."}
    who = _requester()
    now = memory_store._now()
    with memory_store._connect() as conn:
        cur = conn.execute(
            "INSERT INTO feedback (kind, summary, details, reported_by, reported_by_id, via, "
            "bot_version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (kind, summary, details.strip(), who.name, who.user_id or None, who.via,
             bot_version, now, now),
        )
        return {"added": True, **_item_dict(conn, _get(conn, cur.lastrowid))}


def support_item(item_id: int) -> dict:
    who = _requester()
    with memory_store._connect() as conn:
        row = _get(conn, item_id)
        if row is None:
            return {"error": f"No item #{item_id}."}
        if who.user_id and who.user_id == row["reported_by_id"]:
            return {"already_theirs": True, **_item_dict(conn, row)}
        conn.execute(
            "INSERT OR IGNORE INTO feedback_supporters (feedback_id, user_id, name, created_at) "
            "VALUES (?, ?, ?, ?)",
            (item_id, who.user_id, who.name, memory_store._now()),
        )
        return {"supported": True, **_item_dict(conn, row)}


def list_items(kind: str, status: str = "open") -> dict:
    if kind not in KINDS:
        return {"error": f"kind must be one of {', '.join(KINDS)}."}
    with memory_store._connect() as conn:
        if status == "all":
            rows = conn.execute("SELECT * FROM feedback WHERE kind = ? ORDER BY id", (kind,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM feedback WHERE kind = ? AND status = ? ORDER BY id",
                                (kind, status)).fetchall()
        return {"kind": kind, "status_filter": status, "items": [_item_dict(conn, r) for r in rows]}


def _owner_only(action: str) -> dict | None:
    who = _requester()
    if who.is_owner:
        return None
    return {"error": f"Only the bot's owner can {action}. {who.name} isn't the owner - "
                     "anyone can add wishes, report bugs, or back existing ones, though."}


def set_status(item_id: int, status: str, note: str = "") -> dict:
    if denied := _owner_only("change an item's status"):
        return denied
    with memory_store._connect() as conn:
        row = _get(conn, item_id)
        if row is None:
            return {"error": f"No item #{item_id}."}
        allowed = STATUSES[row["kind"]]
        if status not in allowed:
            return {"error": f"A {LABEL[row['kind']]}'s status must be one of {', '.join(allowed)}."}
        conn.execute("UPDATE feedback SET status = ?, status_note = ?, updated_at = ? WHERE id = ?",
                     (status, note.strip(), memory_store._now(), item_id))
        return {"updated": True, **_item_dict(conn, _get(conn, item_id))}


def remove_item(item_id: int) -> dict:
    if denied := _owner_only("remove an item"):
        return denied
    with memory_store._connect() as conn:
        conn.execute("DELETE FROM feedback_supporters WHERE feedback_id = ?", (item_id,))
        cur = conn.execute("DELETE FROM feedback WHERE id = ?", (item_id,))
        if cur.rowcount == 0:
            return {"error": f"No item #{item_id}."}
        return {"removed": True, "id": item_id}


def _issue_url(kind: str, title: str, description: str) -> str:
    query = urllib.parse.urlencode({
        "template": ISSUE_TEMPLATES[kind],
        "title": title,
        "description": description,
        "version": bot_version,
    }, quote_via=urllib.parse.quote)
    return f"{ISSUES_URL}?{query}"


def upstream_link(item_id: int) -> dict:
    """A link that opens a pre-filled GitHub issue for this item. Owner-only,
    because the owner should check it for private details before sending."""
    if denied := _owner_only("send an item to the developer"):
        return denied
    with memory_store._connect() as conn:
        row = _get(conn, item_id)
    if row is None:
        return {"error": f"No item #{item_id}."}
    title = row["summary"][:200]
    description = row["details"] or row["summary"]
    url = _issue_url(row["kind"], title, description)
    shortened = False
    while len(url) > MAX_UPSTREAM_URL and description:
        description = description[:max(0, len(description) - 100)].rstrip()
        shortened = True
        url = _issue_url(row["kind"], title, description + " [...]" if description else "")
    result = {
        "id": item_id,
        "url": url,
        "how_to_use": "Post the url exactly as given, inside <angle brackets>. The owner "
                      "opens it, checks the text for anything private, and submits it. "
                      "Nothing is sent until they do. It needs a GitHub account.",
    }
    if shortened:
        result["shortened"] = ("The details were too long for a link and were cut; "
                               "the owner can paste the rest into the issue.")
    return result


def to_markdown(conn, kind: str) -> str:
    """WISHLIST.md / BUGS.md content, from an open connection (export_db
    passes its consistent snapshot)."""
    title, intro = {
        "wish": ("Loremaster wish list", "Feature ideas from the group, added by asking loremaster in Discord."),
        "bug": ("Loremaster bug reports", "Problems the group reported to loremaster in Discord."),
    }[kind]
    lines = [f"# {title}", "", intro,
             "Generated by `bot/export_db.py` from `loremaster.db` - don't edit by hand.", ""]
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "feedback" not in tables:
        return "\n".join(lines + ["*(Nothing yet.)*", ""])
    for status in STATUSES[kind]:
        rows = conn.execute(
            "SELECT id, summary, details, reported_by, via, bot_version, created_at, status_note "
            "FROM feedback WHERE kind = ? AND status = ? ORDER BY id", (kind, status)).fetchall()
        lines += [f"## {status.capitalize()} ({len(rows)})", ""]
        if not rows:
            lines += ["*(none)*", ""]
            continue
        for item_id, summary, details, reported_by, via, version, created_at, status_note in rows:
            supporters = [r[0] for r in conn.execute(
                "SELECT name FROM feedback_supporters WHERE feedback_id = ? ORDER BY created_at",
                (item_id,))]
            meta = f"{reported_by}, {created_at[:10]}"
            if kind == "bug":
                meta += f", v{version}, via {via}"
            if supporters:
                meta += f"; {'also wanted by' if kind == 'wish' else 'also seen by'} {', '.join(supporters)}"
            lines.append(f"- **#{item_id}** {summary} *({meta})*")
            if details:
                lines.append(f"  - {details}")
            if status_note:
                lines.append(f"  - **{status.capitalize()}:** {status_note}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Claude tool definitions + dispatch
# ---------------------------------------------------------------------------

_KIND_PROP = {"type": "string", "enum": list(KINDS),
              "description": "'wish' = a feature idea for loremaster; 'bug' = something loremaster did wrong."}

TOOLS = [
    {
        "name": "add_feedback",
        "description": (
            "Record feedback about loremaster itself. kind='wish' when someone "
            "wishes the bot could do something ('a wish list item would be...', "
            "'I wish you could...'); kind='bug' when someone reports the bot "
            "misbehaving ('that's a bug', 'you posted that twice', 'report a "
            "bug...'). Call list_feedback for that kind first: if a "
            "substantially similar open item exists, use support_feedback on it "
            "instead of adding a duplicate. Who reported it, how (text/voice), "
            "and the bot version are recorded automatically."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": _KIND_PROP,
                "summary": {"type": "string",
                            "description": "Short, self-contained one-line description."},
                "details": {"type": "string",
                            "description": "Bugs: what they asked or did, what went wrong, "
                                           "and what they expected - from the conversation, "
                                           "enough for a developer to reproduce it. Usually "
                                           "empty for wishes."},
            },
            "required": ["kind", "summary"],
        },
    },
    {
        "name": "support_feedback",
        "description": (
            "Record that the current speaker also wants an existing wish, or "
            "has also seen an existing bug - instead of adding a duplicate."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"item_id": {"type": "integer"}},
            "required": ["item_id"],
        },
    },
    {
        "name": "list_feedback",
        "description": (
            "List wishes or bug reports with who reported them, when, and who "
            "else backs them. Use when someone asks what's on the wish list or "
            "what bugs are known, and before adding an item (to avoid duplicates)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": _KIND_PROP,
                "status": {"type": "string",
                           "enum": ["open", "done", "fixed", "declined", "all"],
                           "description": "Defaults to open. Wishes end as done; bugs as fixed."},
            },
            "required": ["kind"],
        },
    },
    {
        "name": "set_feedback_status",
        "description": (
            "Change an item's status, with an optional short note (e.g. which "
            "version fixed it). Wishes: open/done/declined. Bugs: open/fixed/"
            "declined. Owner-only - the tool enforces this itself, so just call "
            "it and relay any refusal."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "item_id": {"type": "integer"},
                "status": {"type": "string", "enum": ["open", "done", "fixed", "declined"]},
                "note": {"type": "string"},
            },
            "required": ["item_id", "status"],
        },
    },
    {
        "name": "send_feedback_upstream",
        "description": (
            "Make a link that opens a pre-filled GitHub issue for a wish or "
            "bug, so the owner can send it to loremaster's developer. Use when "
            "the owner asks to send, forward or report an item upstream, to "
            "the developer, or to GitHub. Owner-only, enforced by the tool. "
            "The link leaves out who reported or backed the item."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"item_id": {"type": "integer"}},
            "required": ["item_id"],
        },
    },
    {
        "name": "remove_feedback",
        "description": (
            "Delete an item entirely (e.g. added by mistake). Owner-only, "
            "enforced by the tool. Prefer set_feedback_status 'declined' for "
            "real items the owner just won't act on, so the record stays."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"item_id": {"type": "integer"}},
            "required": ["item_id"],
        },
    },
]


def execute_tool(name: str, tool_input: dict) -> str:
    """Dispatch a tool_use block by name; return its tool_result content as
    a JSON string. Never raises - a DB hiccup shouldn't crash the tool loop."""
    try:
        if name == "add_feedback":
            result = add_item(tool_input.get("kind", ""), tool_input.get("summary", ""),
                              tool_input.get("details", ""))
        elif name == "support_feedback":
            result = support_item(int(tool_input.get("item_id", 0)))
        elif name == "list_feedback":
            result = list_items(tool_input.get("kind", ""), tool_input.get("status", "open"))
        elif name == "set_feedback_status":
            result = set_status(int(tool_input.get("item_id", 0)), tool_input.get("status", ""),
                                tool_input.get("note", ""))
        elif name == "remove_feedback":
            result = remove_item(int(tool_input.get("item_id", 0)))
        elif name == "send_feedback_upstream":
            result = upstream_link(int(tool_input.get("item_id", 0)))
        else:
            result = {"error": f"Unknown tool: {name}"}
    except Exception as exc:  # noqa: BLE001 - a DB hiccup shouldn't break the reply
        result = {"error": f"Feedback store error: {exc}"}
    return json.dumps(result)
