"""Optional tool plugins that a game extension can turn on.

A game extension turns plugins on by listing their module names, one per
line, in a plugins.txt file inside its folder (instructions/<game>/plugins.txt).
Lines starting with # are comments. The plugins' tools are offered to Claude
only while a campaign for that game is active.

A plugin module has the same shape as steam_lookup.py:

    TOOLS = [ {Anthropic tool definition}, ... ]
    def execute_tool(name: str, tool_input: dict) -> str: ...  # returns JSON text
"""
