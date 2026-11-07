import json

import memory_store as ms


def test_no_campaign_yet(db, instructions):
    assert ms.get_active_campaign() is None
    assert ms.active_campaign_context() == (None, "")
    assert "error" in ms.get_campaign_state()
    assert "error" in ms.update_campaign_state("notes")
    assert "error" in ms.log_campaign_event("event")


def test_create_needs_an_extension_folder(db, instructions):
    result = ms.create_campaign("Run", "gamma")
    assert "error" in result
    assert "alpha" in result["error"] and "beta" in result["error"]


def test_create_switch_and_list(db, instructions):
    assert ms.create_campaign("First", "alpha") == {"created": "First", "game": "alpha", "active": True}
    assert ms.create_campaign("Second", "beta")["active"]
    assert ms.get_active_campaign()["name"] == "Second"

    assert ms.switch_campaign("First") == {"switched_to": "First", "game": "alpha"}
    campaigns = {c["name"]: c for c in ms.list_campaigns()["campaigns"]}
    assert campaigns["First"]["active"] and not campaigns["Second"]["active"]
    assert ms.active_campaign_context()[0] == "alpha"


def test_duplicate_and_unknown_names(db, instructions):
    ms.create_campaign("Run", "alpha")
    assert "already exists" in ms.create_campaign("Run", "beta")["error"]
    assert "error" in ms.switch_campaign("Nope")


def test_campaign_state_is_per_campaign(db, instructions):
    ms.create_campaign("First", "alpha")
    ms.update_campaign_state("first notes")
    ms.create_campaign("Second", "beta")
    assert ms.get_campaign_state() == {"campaign": "Second", "notes": ""}
    ms.switch_campaign("First")
    assert ms.get_campaign_state()["notes"] == "first notes"


def test_shrink_guard_blocks_big_cuts_unless_confirmed(db, instructions):
    ms.create_campaign("Run", "alpha")
    full = "Party: " + "x" * 200
    assert ms.update_campaign_state(full) == {"updated": "Run"}

    refused = ms.update_campaign_state("[...unchanged...]")
    assert "confirm_shrink" in refused["error"]
    assert ms.get_campaign_state()["notes"] == full

    assert ms.update_campaign_state("short", confirm_shrink=True) == {"updated": "Run"}
    assert ms.get_campaign_state()["notes"] == "short"


def test_small_edits_pass_the_shrink_guard(db, instructions):
    ms.create_campaign("Run", "alpha")
    ms.update_campaign_state("a" * 100)
    assert ms.update_campaign_state("a" * 60) == {"updated": "Run"}


def test_context_includes_state_and_recent_log(db, instructions):
    ms.create_campaign("Run", "alpha")
    ms.update_campaign_state("The party is level 5.")
    ms.log_campaign_event("Beat the dragon")
    game, context = ms.active_campaign_context()
    assert game == "alpha"
    assert "Run" in context and "The party is level 5." in context and "Beat the dragon" in context


def test_general_memory_and_its_shrink_guard(db):
    assert ms.get_general_memory() == {"notes": ""}
    ms.remember_general("We like co-op. " * 20)
    assert "error" in ms.remember_general("gone")
    assert ms.get_general_memory()["notes"].startswith("We like co-op.")


def test_execute_tool_returns_json_and_never_raises(db, instructions, monkeypatch):
    result = json.loads(ms.execute_tool("create_campaign", {"name": "Run", "game": "alpha"}))
    assert result["created"] == "Run"
    assert "Unknown tool" in json.loads(ms.execute_tool("bogus", {}))["error"]

    def boom():
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(ms, "list_campaigns", boom)
    assert "disk on fire" in json.loads(ms.execute_tool("list_campaigns", {}))["error"]


def test_every_tool_is_dispatched(db, instructions):
    """Each tool Claude is offered must reach a real handler."""
    for tool in ms.TOOLS:
        result = json.loads(ms.execute_tool(tool["name"], {}))
        assert "Unknown tool" not in result.get("error", ""), tool["name"]
