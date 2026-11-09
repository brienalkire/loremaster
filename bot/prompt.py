"""Builds the system prompt and the tool set for each Claude call.

Both are rebuilt on every call, not cached, so a switch_campaign tool call
changes the game extension and its plugins on the very next turn, and
edits to instruction files apply without a restart.
"""

import importlib
import json
import re

import dice
import feedback
import memory_store
import paths
import steam_lookup

# Fallback only - used when no campaign has been created or activated yet.
# Once a campaign is active, its own `game` column picks the extension.
GAME_EXTENSION = paths.env_str("GAME_EXTENSION")

INSTRUCTIONS_DIR = paths.INSTRUCTIONS_DIR
CHANGELOG_PATH = paths.CHANGELOG_PATH
# Tool-usage rules that apply under every persona (ships with the code).
CORE_INSTRUCTIONS_PATH = paths.CODE_DIR / "core_instructions.md"


def get_latest_changelog_entry() -> str:
    """Return the top (most recent) version section of CHANGELOG.md,
    heading included - lets the bot answer "what version are you running"
    with the real recent-changes summary, not just a bare number."""
    if not CHANGELOG_PATH.exists():
        return ""
    text = CHANGELOG_PATH.read_text(encoding="utf-8")
    sections = re.split(r"(?m)^## ", text)
    return ("## " + sections[1]).strip() if len(sections) > 1 else ""


def build_system_prompt(version: str) -> str:
    """Rebuilt on every Claude call (not cached) so a mid-conversation
    switch_campaign tool call takes effect on the very next turn without a
    restart - see run_claude_with_tools()."""
    parts = [CORE_INSTRUCTIONS_PATH.read_text(encoding="utf-8"),
             paths.persona_path().read_text(encoding="utf-8")]

    parts.append(
        f"## Bot Version\nRunning loremaster v{version}. If asked what "
        "version you're running or what's new, give the version number and "
        "a short, conversational summary of the changes below (not a raw "
        "dump of this changelog) unless full detail is asked for:\n\n"
        f"{get_latest_changelog_entry()}"
    )

    active_game, campaign_context = memory_store.active_campaign_context()
    game = active_game or GAME_EXTENSION

    extension_dir = INSTRUCTIONS_DIR / game
    if game and extension_dir.is_dir():
        rag_doc = extension_dir / f"instructions_{game}_rag.md"
        if rag_doc.exists():
            parts.append(rag_doc.read_text(encoding="utf-8"))
        project_files_dir = extension_dir / "project_files"
        if project_files_dir.is_dir():
            for path in sorted(project_files_dir.glob("*.md")):
                parts.append(path.read_text(encoding="utf-8"))

    for module in active_tool_modules():
        if getattr(module, "INSTRUCTIONS", None):
            parts.append(module.INSTRUCTIONS)

    if campaign_context:
        parts.append(campaign_context)

    general_notes = memory_store.get_general_memory()["notes"]
    if general_notes:
        parts.append(f"## General memory\n{general_notes}")

    return "\n\n---\n\n".join(parts)


CORE_TOOL_MODULES = [steam_lookup, memory_store, feedback, dice]
_plugin_cache: dict[str, object] = {}


def _load_plugin(name: str):
    """Import plugins/<name>.py once. A plugin that's missing or fails to
    import is logged and skipped, so a typo in plugins.txt can't stop the
    bot from answering."""
    if name not in _plugin_cache:
        try:
            _plugin_cache[name] = importlib.import_module(f"plugins.{name}")
        except Exception as exc:  # noqa: BLE001
            print(f"Tool plugin '{name}' failed to load, skipping it: {exc}", flush=True)
            _plugin_cache[name] = None
    return _plugin_cache[name]


def active_tool_modules() -> list:
    """Core tools plus the plugins the active game's extension lists in
    its plugins.txt (see plugins/__init__.py). Re-read on every Claude call
    so switch_campaign changes the tool set without a restart."""
    game = memory_store.active_campaign_context()[0] or GAME_EXTENSION
    plugins_file = INSTRUCTIONS_DIR / game / "plugins.txt" if game else None
    if not plugins_file or not plugins_file.exists():
        return list(CORE_TOOL_MODULES)
    names = [line.split("#", 1)[0].strip()
             for line in plugins_file.read_text(encoding="utf-8").splitlines()]
    plugins = [_load_plugin(name) for name in names if name]
    return CORE_TOOL_MODULES + [module for module in plugins if module is not None]


# Anthropic's server-side web search: it runs on Anthropic's side during the
# messages.create call, so it never reaches execute_tool_call. Billed per
# search on top of tokens; max_uses caps searches per reply.
WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 3}


def execute_tool_call(name: str, tool_input: dict, modules: list) -> str:
    module = next((m for m in modules if any(t["name"] == name for t in m.TOOLS)), None)
    if module is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    return module.execute_tool(name, tool_input)
