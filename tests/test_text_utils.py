import re

import pytest

from text_utils import (DISCORD_MESSAGE_LIMIT, FILE_TRIGGER_PATTERN, VOICE_MODE_PATTERN,
                        chunk_message, clean_text_for_speech, derive_filename,
                        format_attached_file, strip_attachments_for_history)


@pytest.mark.parametrize("text", [
    "write it up as a file",
    "can I download this?",
    "give it to me in Markdown",
    "send the files",
])
def test_file_trigger_matches(text):
    assert FILE_TRIGGER_PATTERN.search(text)


@pytest.mark.parametrize("text", ["what should we play", "profile of the boss", "refile"])
def test_file_trigger_ignores_other_words(text):
    assert not FILE_TRIGGER_PATTERN.search(text)


@pytest.mark.parametrize("text, mode, state", [
    ("voice on", "voice", "on"),
    ("please SPEAK OFF now", "speak", "off"),
    ("listen   on", "listen", "on"),
])
def test_voice_mode_pattern(text, mode, state):
    match = VOICE_MODE_PATTERN.search(text)
    assert match and match.group(1).lower() == mode and match.group(2).lower() == state


@pytest.mark.parametrize("text", ["voice chat is fun", "turn the voice up", "speaking of which"])
def test_voice_mode_pattern_needs_on_or_off(text):
    assert not VOICE_MODE_PATTERN.search(text)


def test_derive_filename_from_heading():
    assert derive_filename("\n\n## Mira's Build: Level 12!\nbody") == "mira_s_build_level_12.md"


def test_derive_filename_falls_back_to_timestamp():
    assert re.fullmatch(r"loremaster_export_\d{8}_\d{6}\.md", derive_filename("### !!!\n"))


def test_chunk_message_short_text_is_one_chunk():
    assert chunk_message("hello") == ["hello"]
    assert chunk_message("") == []


def test_chunk_message_splits_on_newlines_and_keeps_everything():
    lines = [f"line {i:04d} " + "x" * 80 for i in range(100)]
    text = "\n".join(lines)
    chunks = chunk_message(text)
    assert len(chunks) > 1
    assert all(len(c) <= DISCORD_MESSAGE_LIMIT for c in chunks)
    assert "".join(chunks) == text
    # Every split lands on a line break, not mid-line.
    assert all(c.startswith("\n") for c in chunks[1:])


def test_chunk_message_hard_splits_a_line_with_no_breaks():
    text = "y" * (DISCORD_MESSAGE_LIMIT * 2 + 5)
    chunks = chunk_message(text)
    assert [len(c) for c in chunks] == [DISCORD_MESSAGE_LIMIT, DISCORD_MESSAGE_LIMIT, 5]


def test_attached_file_round_trip():
    text = "\n\n".join(["my question",
                        format_attached_file("a.md", "first\nfile"),
                        format_attached_file("b.txt", "second")])
    stripped = strip_attachments_for_history(text)
    assert "first" not in stripped and "second" not in stripped
    assert "my question" in stripped
    assert "[attached file: a.md" in stripped and "[attached file: b.txt" in stripped


def test_strip_attachments_replaces_images_with_a_marker():
    content = [{"type": "image", "source": {}}, {"type": "image", "source": {}},
               {"type": "text", "text": "what's this?"}]
    stripped = strip_attachments_for_history(content)
    assert stripped.startswith("[2 image attachment(s)")
    assert stripped.endswith("what's this?")


def test_strip_attachments_text_blocks_without_images():
    content = [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
    assert strip_attachments_for_history(content) == "a\n\nb"


def test_clean_text_for_speech():
    text = ("# Title\n**bold** and __bold__, *italic* and _italic_, `code`, "
            "[a link](https://example.com)\n\n---\n\n\n\nend snake_case_word")
    assert clean_text_for_speech(text) == (
        "Title\nbold and bold, italic and italic, code, a link\n\nend snake_case_word")
