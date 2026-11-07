"""Text handling for Discord messages: command patterns, attachment
markers, splitting long replies, and cleaning text for speech. No Discord
or model imports, so it is cheap to import and test."""

import re
from datetime import datetime

DISCORD_MESSAGE_LIMIT = 2000

# Mentioning "file", "download", or "markdown" anywhere asks the bot to
# reply with a downloadable .md file instead of a chat message. Broad
# word-boundary match, not exact phrases — natural phrasing varies too much
# ("give me a file", "as a file", "can I download this", ...) for a fixed
# phrase list to catch reliably; a false-positive just means an unrelated
# reply arrives as a file, which is harmless.
FILE_TRIGGER_PATTERN = re.compile(r"\b(file|download|markdown)\w*\b", re.IGNORECASE)

# "voice on"/"voice off" toggle both listening (STT) and speaking (TTS)
# together; "listen on/off" and "speak on/off" control each independently.
# Not per-user or per-game yet — see bot/README.md.
VOICE_MODE_PATTERN = re.compile(r"\b(voice|listen|speak)\s+(on|off)\b", re.IGNORECASE)


def derive_filename(text: str) -> str:
    first_line = next((line for line in text.splitlines() if line.strip()), "")
    heading = re.sub(r"^#+\s*", "", first_line).strip()
    slug = re.sub(r"[^a-z0-9]+", "_", heading.lower()).strip("_")
    if not slug:
        slug = f"loremaster_export_{datetime.now():%Y%m%d_%H%M%S}"
    return f"{slug}.md"


def format_attached_file(filename: str, file_text: str) -> str:
    """Wrap a text attachment's content so strip_attachments_for_history
    can find and replace it later."""
    return f"--- ATTACHED_FILE: {filename} ---\n{file_text}\n--- END_ATTACHED_FILE ---"


# Matches the ATTACHED_FILE wrapper build_user_content() wraps text-
# attachment content in - non-greedy so multiple attachments in one
# message each get stripped individually, not collapsed into one match.
ATTACHED_FILE_PATTERN = re.compile(
    r"--- ATTACHED_FILE: (.+?) ---\n.*?\n--- END_ATTACHED_FILE ---", re.DOTALL,
)


def _strip_attached_files(text: str) -> str:
    return ATTACHED_FILE_PATTERN.sub(
        lambda m: f"[attached file: {m.group(1)} — omitted here to save space]", text
    )


def strip_attachments_for_history(content):
    """Replace image blocks and embedded attached-file text with short
    markers once a turn has been answered — resending full attachment
    content on every future request in the channel (the API is stateless)
    is how a single upload balloons into a 413 a few turns later."""
    if isinstance(content, str):
        return _strip_attached_files(content)
    image_count = sum(1 for b in content if b.get("type") == "image")
    text_parts = [_strip_attached_files(b["text"]) for b in content if b.get("type") == "text"]
    if not image_count:
        return "\n\n".join(text_parts)
    marker = f"[{image_count} image attachment(s) — omitted here to save space]"
    return "\n\n".join([marker, *text_parts])


def chunk_message(text: str, limit: int = DISCORD_MESSAGE_LIMIT) -> list[str]:
    chunks = []
    while len(text) > limit:
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:]
    if text:
        chunks.append(text)
    return chunks


def clean_text_for_speech(text: str) -> str:
    """Strip markdown formatting from a chat reply before sending it to TTS.

    Adapted from podcast_generator's strip_markdown(), but only the inline-
    formatting substitutions apply here. That script's other steps assume a
    structured podcast script — dropping **Key:** metadata lines and, most
    importantly, stopping output entirely at the first italic-only line (a
    script's trailing production note) — and would silently truncate a
    normal chat reply that happens to contain an italicized sentence.
    """
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)          # headers -> plain text
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)                    # **bold**
    text = re.sub(r"__([^_]+)__", r"\1", text)                        # __bold__
    text = re.sub(r"\*([^*]+)\*", r"\1", text)                        # *italic*
    text = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", text)             # _italic_
    text = re.sub(r"`([^`]+)`", r"\1", text)                          # `code`
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)              # [text](url)
    text = re.sub(r"^\s*([-*_])\1{2,}\s*$", "", text, flags=re.MULTILINE)  # horizontal rules
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
