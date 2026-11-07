import json
import sqlite3

import feedback as fb


def test_add_records_who_and_how(db, requester, monkeypatch):
    monkeypatch.setattr(fb, "bot_version", "9.9.9")
    requester(user_id=7, name="Alice", via="voice")
    item = fb.add_item("bug", "  answered twice  ", "asked once, got two replies")
    assert item["added"] and item["id"] == 1
    assert item["summary"] == "answered twice"
    assert item["reported_by"] == "Alice"
    assert item["via"] == "voice" and item["bot_version"] == "9.9.9"
    assert item["status"] == "open"


def test_add_rejects_bad_input(db, requester):
    requester()
    assert "error" in fb.add_item("idea", "something")
    assert "error" in fb.add_item("wish", "   ")


def test_without_a_requester_it_is_someone(db):
    assert fb.add_item("wish", "dark mode")["reported_by"] == "Someone"


def test_support_adds_backers_once(db, requester):
    requester(user_id=1, name="Alice")
    wish = fb.add_item("wish", "track loot")
    requester(user_id=2, name="Bob")
    fb.support_item(wish["id"])
    fb.support_item(wish["id"])
    requester(user_id=3, name="Cara")
    result = fb.support_item(wish["id"])
    assert result["supported"]
    assert result["also_wanted_by"] == ["Bob", "Cara"]


def test_cant_back_your_own_item(db, requester):
    requester(user_id=1, name="Alice")
    wish = fb.add_item("wish", "track loot")
    assert fb.support_item(wish["id"])["already_theirs"]
    assert "error" in fb.support_item(999)


def test_list_filters_by_kind_and_status(db, requester):
    requester(is_owner=True)
    w1 = fb.add_item("wish", "one")
    fb.add_item("wish", "two")
    fb.add_item("bug", "three")
    fb.set_status(w1["id"], "done")
    assert [i["summary"] for i in fb.list_items("wish")["items"]] == ["two"]
    assert [i["summary"] for i in fb.list_items("wish", "all")["items"]] == ["one", "two"]
    assert [i["summary"] for i in fb.list_items("bug")["items"]] == ["three"]
    assert "error" in fb.list_items("idea")


def test_only_the_owner_changes_status_or_removes(db, requester):
    requester(user_id=1, name="Alice")
    bug = fb.add_item("bug", "crash")
    assert "Only the bot's owner" in fb.set_status(bug["id"], "fixed")["error"]
    assert "Only the bot's owner" in fb.remove_item(bug["id"])["error"]
    assert fb.list_items("bug")["items"][0]["status"] == "open"


def test_owner_status_values_depend_on_kind(db, requester):
    requester(is_owner=True)
    bug = fb.add_item("bug", "crash")
    wish = fb.add_item("wish", "maps")
    assert "error" in fb.set_status(bug["id"], "done")
    assert "error" in fb.set_status(wish["id"], "fixed")
    fixed = fb.set_status(bug["id"], "fixed", "patched in 1.2")
    assert fixed["status"] == "fixed" and fixed["status_note"] == "patched in 1.2"
    assert "error" in fb.set_status(999, "fixed")


def test_owner_removes_item_and_its_backers(db, requester):
    requester(user_id=1, name="Alice")
    wish = fb.add_item("wish", "maps")
    requester(user_id=2, name="Bob")
    fb.support_item(wish["id"])
    requester(user_id=3, is_owner=True)
    assert fb.remove_item(wish["id"]) == {"removed": True, "id": wish["id"]}
    assert "error" in fb.remove_item(wish["id"])
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM feedback_supporters").fetchone()[0] == 0


def test_to_markdown_lists_items(db, requester):
    requester(user_id=1, name="Alice")
    fb.add_item("wish", "track loot")
    fb.add_item("bug", "answered twice")
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        wishes = fb.to_markdown(conn, "wish")
    assert "- **#1**" in wishes and "track loot" in wishes
    assert "answered twice" not in wishes


def test_execute_tool_dispatches_and_returns_json(db, requester):
    requester()
    added = json.loads(fb.execute_tool("add_feedback", {"kind": "wish", "summary": "maps"}))
    assert added["added"]
    listed = json.loads(fb.execute_tool("list_feedback", {"kind": "wish"}))
    assert len(listed["items"]) == 1
    assert "Unknown tool" in json.loads(fb.execute_tool("bogus", {}))["error"]
    for tool in fb.TOOLS:
        result = json.loads(fb.execute_tool(tool["name"], {}))
        assert "Unknown tool" not in result.get("error", ""), tool["name"]
