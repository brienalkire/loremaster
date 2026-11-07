"""Shared test setup.

The bot's modules read LOREMASTER_HOME when they're first imported, so it's
set here, before any test imports them, to an empty temporary folder. That
keeps tests away from a real .env, database and instructions. Each test
that touches the database gets its own file through the `db` fixture.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
BOT = REPO / "bot"

os.environ["LOREMASTER_HOME"] = tempfile.mkdtemp(prefix="loremaster-test-home-")
for name in ("GAME_EXTENSION", "LOREMASTER_VOICE_INPUT", "LOREMASTER_WAKE_WORD",
             "LOREMASTER_WAKE_WORD_ALIASES"):
    os.environ.pop(name, None)
sys.path.insert(0, str(BOT))

import feedback  # noqa: E402
import memory_store  # noqa: E402


@pytest.fixture
def db(tmp_path, monkeypatch):
    """A fresh, empty database for one test."""
    monkeypatch.setattr(memory_store, "DB_PATH", tmp_path / "test.db")
    memory_store.init_db()
    feedback.init_db()
    return tmp_path / "test.db"


@pytest.fixture
def instructions(tmp_path, monkeypatch):
    """An instructions/ folder with a persona and two game extensions, used
    by memory_store and prompt in place of the real one."""
    import prompt

    root = tmp_path / "instructions"
    (root / "alpha" / "project_files").mkdir(parents=True)
    (root / "beta").mkdir()
    (root / "persona.md").write_text("PERSONA TEXT", encoding="utf-8")
    (root / "alpha" / "instructions_alpha_rag.md").write_text("ALPHA RAG", encoding="utf-8")
    (root / "alpha" / "project_files" / "b_notes.md").write_text("ALPHA NOTES B", encoding="utf-8")
    (root / "alpha" / "project_files" / "a_notes.md").write_text("ALPHA NOTES A", encoding="utf-8")
    (root / "beta" / "instructions_beta_rag.md").write_text("BETA RAG", encoding="utf-8")

    import paths
    monkeypatch.setattr(paths, "INSTRUCTIONS_DIR", root)
    monkeypatch.setattr(memory_store, "INSTRUCTIONS_DIR", root)
    monkeypatch.setattr(prompt, "INSTRUCTIONS_DIR", root)
    monkeypatch.setattr(prompt, "GAME_EXTENSION", "")
    monkeypatch.setattr(prompt, "_plugin_cache", {})
    return root


@pytest.fixture
def requester():
    """Set who's asking, the way main.py does before each Claude call.
    Call it with a Requester; the previous one comes back afterwards."""
    tokens = []

    def set_requester(user_id=1, name="Alice", is_owner=False, via="text"):
        who = feedback.Requester(user_id=user_id, name=name, is_owner=is_owner, via=via)
        tokens.append(feedback.current_requester.set(who))
        return who

    yield set_requester
    for token in reversed(tokens):
        feedback.current_requester.reset(token)
