"""paths.py decides where everything lives when it's first imported, so
each layout is checked in a fresh Python process."""

import json
import os
import subprocess
import sys

import pytest

import paths
from conftest import BOT

PROBE = (
    "import json, paths; print(json.dumps({k: str(getattr(paths, k)) for k in "
    "('HOME', 'DATA_DIR', 'DB_PATH', 'LOG_PATH', 'WISHLIST_PATH', 'INSTRUCTIONS_DIR')}))"
)


def probe(home=None, cwd=None):
    env = {k: v for k, v in os.environ.items() if k != "LOREMASTER_HOME"}
    if home is not None:
        env["LOREMASTER_HOME"] = str(home)
    out = subprocess.run([sys.executable, "-c", PROBE], cwd=cwd or BOT, env=env,
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_home_holds_data_and_falls_back_to_example_instructions(tmp_path):
    home = tmp_path / "new" / "home"
    result = probe(home)
    assert result["HOME"] == str(home)
    assert result["DATA_DIR"] == str(home)
    assert result["DB_PATH"] == str(home / "loremaster.db")
    assert result["WISHLIST_PATH"] == str(home / "WISHLIST.md")
    assert result["INSTRUCTIONS_DIR"] == str(paths.EXAMPLE_INSTRUCTIONS_DIR)
    assert home.is_dir()  # created on first use


def test_home_instructions_win_over_examples(tmp_path):
    (tmp_path / "instructions").mkdir()
    assert probe(tmp_path)["INSTRUCTIONS_DIR"] == str(tmp_path / "instructions")


def test_env_file_in_home_is_loaded(tmp_path):
    (tmp_path / ".env").write_text("LOREMASTER_TEST_SETTING=from-env-file\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "LOREMASTER_TEST_SETTING"}
    env["LOREMASTER_HOME"] = str(tmp_path)
    out = subprocess.run(
        [sys.executable, "-c", "import paths; print(paths.env_str('LOREMASTER_TEST_SETTING'))"],
        cwd=BOT, env=env, capture_output=True, text=True, check=True).stdout
    assert out.strip() == "from-env-file"


def test_example_persona_ships_with_the_code():
    assert (paths.EXAMPLE_INSTRUCTIONS_DIR / "persona.md").exists()
    assert (paths.EXAMPLE_INSTRUCTIONS_DIR / "example_game" / "instructions_example_game_rag.md").exists()


def test_missing_persona_explains_what_to_do(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "INSTRUCTIONS_DIR", tmp_path)
    with pytest.raises(FileNotFoundError, match="persona.md"):
        paths.persona_path()


@pytest.mark.parametrize("value, expected", [
    ("", False), ("true", True), ("TRUE", True), ("1", True), ("yes", True), ("on", True),
    ("false", False), ("0", False), ("off", False),
])
def test_env_bool(monkeypatch, value, expected):
    monkeypatch.setenv("LOREMASTER_TEST_BOOL", value)
    assert paths.env_bool("LOREMASTER_TEST_BOOL") is expected


def test_env_bool_default(monkeypatch):
    monkeypatch.delenv("LOREMASTER_TEST_BOOL", raising=False)
    assert paths.env_bool("LOREMASTER_TEST_BOOL", True) is True


def test_env_str_list_and_int(monkeypatch):
    monkeypatch.setenv("LOREMASTER_TEST_STR", "  padded  ")
    monkeypatch.setenv("LOREMASTER_TEST_LIST", " Warmaster, ,LORE master ,")
    monkeypatch.setenv("LOREMASTER_TEST_INT", "10301")
    monkeypatch.setenv("LOREMASTER_TEST_BLANK", "   ")
    assert paths.env_str("LOREMASTER_TEST_STR") == "padded"
    assert paths.env_str("LOREMASTER_TEST_BLANK", "fallback") == "fallback"
    assert paths.env_list("LOREMASTER_TEST_LIST") == ("warmaster", "lore master")
    assert paths.env_int("LOREMASTER_TEST_INT", 1) == 10301
    assert paths.env_int("LOREMASTER_TEST_MISSING", 10300) == 10300
