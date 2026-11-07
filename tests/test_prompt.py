import json
import sys
import types

import feedback
import memory_store as ms
import prompt
import steam_lookup

CORE = [steam_lookup, ms, feedback]


def test_no_campaign_uses_core_tools_and_persona(db, instructions):
    assert prompt.active_tool_modules() == CORE
    text = prompt.build_system_prompt("1.2.3")
    # The core instructions contain --- lines of their own, so check the
    # joins around the persona rather than splitting on the separator.
    assert text.startswith("# Loremaster – Core Instructions")
    assert "\n\n---\n\nPERSONA TEXT\n\n---\n\n## Bot Version\nRunning loremaster v1.2.3." in text
    assert "RAG" not in text


def test_game_extension_setting_is_the_fallback(db, instructions, monkeypatch):
    monkeypatch.setattr(prompt, "GAME_EXTENSION", "beta")
    assert "BETA RAG" in prompt.build_system_prompt("1")


def test_active_campaign_loads_its_extension_in_order(db, instructions):
    ms.create_campaign("Run", "alpha")
    ms.update_campaign_state("Party is level 5.")
    ms.remember_general("Group likes co-op.")
    text = prompt.build_system_prompt("1")
    order = ["PERSONA TEXT", "Running loremaster", "ALPHA RAG", "ALPHA NOTES A", "ALPHA NOTES B",
             "Party is level 5.", "## General memory\nGroup likes co-op."]
    positions = [text.index(marker) for marker in order]
    assert positions == sorted(positions)
    assert "BETA RAG" not in text


def test_switching_campaign_switches_extension(db, instructions):
    ms.create_campaign("A", "alpha")
    ms.create_campaign("B", "beta")
    assert "BETA RAG" in prompt.build_system_prompt("1")
    ms.switch_campaign("A")
    text = prompt.build_system_prompt("1")
    assert "ALPHA RAG" in text and "BETA RAG" not in text


def test_old_persona_file_name_still_works(db, instructions):
    (instructions / "persona.md").rename(instructions / "instructions_gameassistant_base.md")
    assert "PERSONA TEXT" in prompt.build_system_prompt("1")


def _fake_plugin(monkeypatch, name, tools=("fake_tool",), instructions=None):
    module = types.ModuleType(f"plugins.{name}")
    module.TOOLS = [{"name": t, "description": "", "input_schema": {"type": "object"}} for t in tools]
    module.execute_tool = lambda tool, args: json.dumps({"ran": tool, "args": args})
    if instructions:
        module.INSTRUCTIONS = instructions
    monkeypatch.setitem(sys.modules, f"plugins.{name}", module)
    return module


def test_plugins_load_from_plugins_txt(db, instructions, monkeypatch):
    plugin = _fake_plugin(monkeypatch, "fakeplug", instructions="FAKE PLUGIN GUIDE")
    (instructions / "alpha" / "plugins.txt").write_text(
        "# comment line\n\nfakeplug  # trailing comment\n", encoding="utf-8")
    ms.create_campaign("Run", "alpha")
    assert prompt.active_tool_modules() == CORE + [plugin]
    assert "FAKE PLUGIN GUIDE" in prompt.build_system_prompt("1")

    ms.create_campaign("Other", "beta")
    assert prompt.active_tool_modules() == CORE
    assert "FAKE PLUGIN GUIDE" not in prompt.build_system_prompt("1")


def test_a_broken_plugin_is_skipped(db, instructions, monkeypatch, capsys):
    plugin = _fake_plugin(monkeypatch, "goodplug")
    (instructions / "alpha" / "plugins.txt").write_text("no_such_plugin\ngoodplug\n", encoding="utf-8")
    ms.create_campaign("Run", "alpha")
    assert prompt.active_tool_modules() == CORE + [plugin]
    assert "no_such_plugin" in capsys.readouterr().out


def test_enshrouded_plugin_is_a_valid_plugin():
    import importlib
    module = importlib.import_module("plugins.enshrouded_lookup")
    assert {t["name"] for t in module.TOOLS} == {"lookup_enshrouded_item", "lookup_enshrouded_recipe"}
    assert "Shrouded Tools" in module.INSTRUCTIONS


def test_execute_tool_call_routes_by_name(monkeypatch):
    plugin = _fake_plugin(monkeypatch, "routeplug", tools=("one", "two"))
    modules = CORE + [plugin]
    assert json.loads(prompt.execute_tool_call("two", {"x": 1}, modules)) == {"ran": "two", "args": {"x": 1}}
    assert "Unknown tool" in json.loads(prompt.execute_tool_call("three", {}, modules))["error"]
    # A plugin tool isn't reachable when its plugin isn't active.
    assert "Unknown tool" in json.loads(prompt.execute_tool_call("one", {}, CORE))["error"]


def test_tool_names_are_unique():
    names = [t["name"] for m in CORE for t in m.TOOLS] + [prompt.WEB_SEARCH_TOOL["name"]]
    assert len(names) == len(set(names))


def test_latest_changelog_entry(tmp_path, monkeypatch):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\nintro\n\n## [1.1] - new\n- b\n\n## [1.0]\n- a\n", encoding="utf-8")
    monkeypatch.setattr(prompt, "CHANGELOG_PATH", changelog)
    assert prompt.get_latest_changelog_entry() == "## [1.1] - new\n- b"
    monkeypatch.setattr(prompt, "CHANGELOG_PATH", tmp_path / "missing.md")
    assert prompt.get_latest_changelog_entry() == ""
