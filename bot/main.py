"""Minimal Discord bot that relays @mentions to Claude.

Loads the persona (instructions/persona.md under LOREMASTER_HOME, see paths.py), plus the active
campaign's game extension (base file + its rag doc + project_files/*.md)
and persisted campaign/general memory (see memory_store.py), as the system
prompt. Responds only when @mentioned. Per-channel conversation history is
still in-memory only (lost on restart) — durable campaign state lives in
memory_store's SQLite database instead.
"""

__version__ = "0.6.0"  # keep in sync with CHANGELOG.md and the git tag

import asyncio
import base64
import io
import logging
import os
import re
import sys
import threading
import time
from datetime import datetime


class TimestampedStream:
    """Wraps stdout/stderr so every line written gets a date/time prefix.

    Covers everything that reaches the log - our own print()s, warnings,
    logging output (including voxport's Kokoro progress) and tracebacks - without
    touching each call site. Without timestamps, matching log errors to
    events (e.g. Windows' network-drop log) is guesswork.
    """

    _lock = threading.Lock()  # shared: stdout and stderr go to the same file

    def __init__(self, stream):
        self._stream = stream
        self._at_line_start = True

    def write(self, text: str) -> int:
        if not text:
            return 0
        with self._lock:
            stamp = f"{datetime.now():%m-%d %H:%M:%S} "
            out = []
            for piece in re.findall(r"[^\n]*\n|[^\n]+", text):
                if self._at_line_start:
                    out.append(stamp)
                out.append(piece)
                self._at_line_start = piece.endswith("\n")
            self._stream.write("".join(out))
        return len(text)

    def flush(self) -> None:
        self._stream.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


# Before logging.basicConfig, which binds its handler to sys.stderr as it is
# at that moment. (pythonw with no redirect leaves these as None.)
if sys.stdout is not None:
    sys.stdout = TimestampedStream(sys.stdout)
if sys.stderr is not None:
    sys.stderr = TimestampedStream(sys.stderr)

# py-cord's voice internals report problems (including ones that silently
# end a recording/listening session) via Python's logging module rather
# than raising - see bot/README.md's Voice Input section. Without this,
# those failures are completely invisible.
logging.basicConfig(level=logging.WARNING, format="%(name)s %(levelname)s: %(message)s")


class OneLineReconnectFilter(logging.Filter):
    """Shrink py-cord's reconnect messages to one line.

    discord.client logs every gateway reconnect with _log.exception(), so a
    routine network blip (PC asleep, Wi-Fi drop, DNS briefly down) dumps a
    ~60-line traceback that reads like a crash. The client recovers on its
    own; the exception type and message are all that's worth keeping.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info and str(record.msg).startswith("Attempting a reconnect"):
            exc = record.exc_info[1]
            # msg is still %-formatted with record.args later, so escape any
            # % in the exception text.
            detail = f"{type(exc).__name__}: {exc}".replace("%", "%%")
            record.msg = f"{record.msg} ({detail})"
            record.exc_info = None
            record.exc_text = None
        return True


logging.getLogger("discord.client").addFilter(OneLineReconnectFilter())

# voxport 0.5.0+ logs Kokoro progress (model load, each synthesis) at INFO
# instead of printing it. Keep it in the log: the model-load line is how
# a slow startup shows up. (Per-segment lines are DEBUG and stay hidden.)
logging.getLogger("voxport").setLevel(logging.INFO)

import anthropic
import discord
import soundfile as sf
from PIL import Image
from voxport.stt.wyoming_whisper import WyomingWhisperSTT
from voxport.tts.kokoro_direct import KokoroDirectTTS

# Works around a real bug (Pycord-Development/pycord#3388): UDPKeepAlive
# defaults to a 5000-SECOND delay, so voice receive silently drops audio
# after ~5-9 minutes without this patch. Must happen before any voice
# connection - see bot/README.md's Voice Input section for the full story
# behind depending on this pinned py-cord commit at all.
from discord.voice.receive.reader import UDPKeepAlive
UDPKeepAlive.delay = 5

# Works around a second receive bug in the same pinned commit: JitterBuffer
# drops any packet whose RTP sequence number is >10000 ahead of (or at all
# behind) the last one it delivered, as "old" - and never advances past
# them. So if a speaker's sequence counter jumps, every packet from them is
# silently discarded until the 16-bit counter wraps back around: up to
# ~20 minutes of speech at 50 packets/s, logged only at DEBUG. A lone late
# packet is still dropped as before; a run of them means the sender's
# sequence moved, so resync to it instead.
from discord.voice.utils.buffer import JitterBuffer

JITTER_RESYNC_AFTER_DROPS = 10
_original_jitter_push = JitterBuffer.push


def _resyncing_jitter_push(self, packet) -> bool:
    if _original_jitter_push(self, packet):
        self._consecutive_old_drops = 0
        return True
    self._consecutive_old_drops = getattr(self, "_consecutive_old_drops", 0) + 1
    if self._consecutive_old_drops < JITTER_RESYNC_AFTER_DROPS:
        return False
    print(f"[voice] {datetime.now():%H:%M:%S} RTP sequence jump detected "
          f"(last delivered seq={self._last_tx_seq}, now seq={packet.sequence}) - "
          f"resyncing jitter buffer", flush=True)
    self._consecutive_old_drops = 0
    self.reset()
    return _original_jitter_push(self, packet)


JitterBuffer.push = _resyncing_jitter_push


# Works around a third receive bug in the same pinned commit: the voice
# socket reader thread hands each packet to the event loop with a plain
# loop.create_task() (discord/voice/state.py, SocketReader._do_run), which
# isn't thread-safe and never wakes the loop - so packets sit queued until
# something unrelated (a heartbeat, a timer) wakes it, measured live at a
# steady ~5s recv->processing lag. Wake the loop after any off-thread
# create_task, exactly as call_soon_threadsafe does. Must be installed from
# the loop's own thread (on_ready).
def make_loop_create_task_threadsafe(loop: asyncio.AbstractEventLoop) -> None:
    if getattr(loop, "_threadsafe_create_task_patched", False):
        return
    original_create_task = loop.create_task
    loop_thread_id = threading.get_ident()

    def create_task(coro, **kwargs):
        task = original_create_task(coro, **kwargs)
        if threading.get_ident() != loop_thread_id:
            loop._write_to_self()
        return task

    loop.create_task = create_task
    loop._threadsafe_create_task_patched = True

import paths  # loads LOREMASTER_HOME/.env - must come before anything reads a setting
import memory_store
import voice_input
import feedback
from prompt import WEB_SEARCH_TOOL, active_tool_modules, build_system_prompt, execute_tool_call
from text_utils import (FILE_TRIGGER_PATTERN, VOICE_MODE_PATTERN, chunk_message,
                        clean_text_for_speech, derive_filename, format_attached_file,
                        strip_attachments_for_history)

DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL") or "claude-sonnet-5"

memory_store.init_db()
feedback.init_db()
feedback.bot_version = __version__


# Sonnet 5 runs adaptive (extended) thinking by default even when `thinking`
# is omitted, and a thinking block that fills max_tokens leaves no room for
# the actual text reply (see the empty-reply diagnostic below) — so this
# needs real headroom, not a small chat-reply-sized cap.
MAX_TOKENS = 16000
MAX_HISTORY_MESSAGES = 40  # ~20 user/assistant exchanges, per channel

# Cap on tool-call round trips per reply, so a confused loop (Claude keeps
# calling tools without ever producing a final answer) can't run forever.
MAX_TOOL_ITERATIONS = 5

# Kokoro voice for spoken replies (LOREMASTER_TTS_VOICE in .env). One voice
# for the whole bot - no per-game or per-user voices yet.
TTS_VOICE = paths.env_str("LOREMASTER_TTS_VOICE", "bm_george")

# Matches the bot's own name - said after this anywhere in a transcribed
# voice utterance, the rest of that utterance becomes the query. Utterances
# that don't contain it are ignored, same as text messages that don't
# @mention the bot.
WAKE_WORD = paths.env_str("LOREMASTER_WAKE_WORD", "loremaster").lower()

# Extra spellings that also count as the wake word (comma-separated
# LOREMASTER_WAKE_WORD_ALIASES). For words Whisper consistently mishears
# just below the fuzzy-match threshold - for example, a name in the group
# that sounds like the wake word.
WAKE_WORD_ALIASES = paths.env_list("LOREMASTER_WAKE_WORD_ALIASES")

# Real-time voice input (STT). Its long-chased multi-minute "packet stalls"
# turned out to be voice_client.stop() silently stopping voice receive
# whenever a spoken reply interrupted another (fixed in play_speech, along
# with the other receive bugs patched above). Experimental, so off unless
# LOREMASTER_VOICE_INPUT=true: it records people and needs a separate
# Wyoming Whisper server (WHISPER_HOST / WHISPER_PORT). When off, "listen
# on" refuses with an explanation and "voice on" only turns on speaking -
# see handle_voice_mode_toggle.
STT_ENABLED = paths.env_bool("LOREMASTER_VOICE_INPUT", False)

IMAGE_MEDIA_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                      "gif": "image/gif", "webp": "image/webp"}

# Anthropic's recommended max long-edge for vision input — larger images get
# downscaled server-side anyway, so resizing client-side just avoids hitting
# request-size limits (Discord screenshots, especially from phones, can be
# several MB) without losing anything Claude would have used regardless.
MAX_IMAGE_DIMENSION = 1568
IMAGE_JPEG_QUALITY = 85

TEXT_ATTACHMENT_EXTENSIONS = {"md", "txt"}
# Keeps one huge upload from blowing out the request/context budget -
# generous enough for anything this bot's exports (character write-ups,
# guides) would realistically produce.
MAX_ATTACHMENT_CHARS = 50_000

anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
tts_engine = KokoroDirectTTS()
stt_engine = WyomingWhisperSTT(host=paths.env_str("WHISPER_HOST", "localhost"),
                               port=paths.env_int("WHISPER_PORT", 10300))  # see voxport/stt_guidance.md

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
discord_client = discord.Client(intents=intents)

# In-memory conversation history, keyed by channel ID. Lost on restart.
channel_history: dict[int, list[dict]] = {}

# Per-channel listen (STT) / speak (TTS) toggles, keyed by text channel ID.
# Note: discord.py/py-cord hold at most one voice connection per guild, so
# if two different text channels in the same guild both toggle voice on,
# the most recent toggle wins the actual connection even though both
# channels' entries read True — fine for this bot's normal usage (one
# active channel per server) but not true per-channel isolation.
channel_listen_enabled: dict[int, bool] = {}
channel_speak_enabled: dict[int, bool] = {}

# Which text channel a guild's voice-triggered replies get posted into,
# keyed by guild ID — set when listening starts, since a wake-word
# utterance arrives via the voice connection with no text channel of its
# own attached.
guild_text_targets: dict[int, int] = {}

# Natural speech often pauses after the wake word before the actual
# question ("Loremaster," <pause>, "what should we play") - real-time VAD
# segments that into two separate utterances, and each is normally checked
# for the wake word in isolation. This tracks "just heard the wake word
# alone from this speaker" (uid -> monotonic timestamp) so the NEXT
# utterance from them, within the window below, counts as the query even
# without repeating the wake word.
awaiting_voice_query: dict[int, float] = {}
WAKE_WORD_PRIMED_WINDOW_S = 8.0


def is_image_attachment(attachment: discord.Attachment) -> bool:
    if attachment.content_type:
        media_type = attachment.content_type.split(";")[0].strip().lower()
        if media_type in IMAGE_MEDIA_TYPES.values():
            return True
    ext = attachment.filename.rsplit(".", 1)[-1].lower() if "." in attachment.filename else ""
    return ext in IMAGE_MEDIA_TYPES


def is_text_attachment(attachment: discord.Attachment) -> bool:
    ext = attachment.filename.rsplit(".", 1)[-1].lower() if "." in attachment.filename else ""
    return ext in TEXT_ATTACHMENT_EXTENSIONS


def shrink_image(image_bytes: bytes) -> tuple[bytes, str]:
    """Downscale + recompress as JPEG so large screenshots (phone captures
    can easily be 8-10MB) don't blow past the API's request-size limit."""
    img = Image.open(io.BytesIO(image_bytes))
    img = img.convert("RGB")
    img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=IMAGE_JPEG_QUALITY)
    return out.getvalue(), "image/jpeg"


async def build_user_content(message: discord.Message, text: str):
    """Return plain text, or (if image attachments are present) a list of
    Anthropic content blocks combining the images with the text. Text/
    markdown attachments get their content folded directly into the text
    (wrapped in ATTACHED_FILE markers - see strip_attachments_for_history)
    rather than a separate block, since the API has no special type for
    plain text files."""
    image_blocks = []
    attached_text_parts = []
    for attachment in message.attachments:
        if is_image_attachment(attachment):
            image_bytes = await attachment.read()
            try:
                image_bytes, media_type = shrink_image(image_bytes)
            except Exception as exc:
                print(f"Image shrink failed for {attachment.filename}: {exc}", flush=True)
                continue
            image_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64.b64encode(image_bytes).decode("ascii"),
                },
            })
        elif is_text_attachment(attachment):
            raw_bytes = await attachment.read()
            try:
                file_text = raw_bytes.decode("utf-8")
            except UnicodeDecodeError as exc:
                print(f"Attachment decode failed for {attachment.filename}: {exc}", flush=True)
                continue
            if len(file_text) > MAX_ATTACHMENT_CHARS:
                file_text = file_text[:MAX_ATTACHMENT_CHARS] + "\n[...truncated...]"
            attached_text_parts.append(format_attached_file(attachment.filename, file_text))

    if attached_text_parts:
        text = "\n\n".join([text, *attached_text_parts]) if text else "\n\n".join(attached_text_parts)

    if not image_blocks:
        return text
    return [*image_blocks, {"type": "text", "text": text}]


# One synthesis at a time. KokoroDirectTTS loads its model lazily with no
# lock, so replies arriving together each loaded their own copy at once -
# and with a game also on the GPU, three models plus three syntheses ran
# out of VRAM and stalled for minutes (2026-10-11, Enshrouded running).
_tts_lock = threading.Lock()
tts_warmed_up = False  # set by the first on_ready; see there


def synthesize_speech_wav(text: str) -> bytes:
    """Synthesize `text` and return it encoded as WAV bytes.

    Blocking/CPU-bound — always run this via asyncio.to_thread(), never
    called directly from the event loop.
    """
    with _tts_lock:
        audio = tts_engine.synthesize(text, TTS_VOICE)
    buf = io.BytesIO()
    sf.write(buf, audio, tts_engine.sample_rate, format="WAV")
    return buf.getvalue()


def warm_up_tts() -> None:
    """Load the TTS model with a throwaway synthesis. Blocking - run via
    asyncio.to_thread(). Failure is logged, not fatal: speech just falls
    back to loading on first use."""
    try:
        synthesize_speech_wav("Ready.")
        print("TTS model loaded.", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"TTS warm-up failed: {exc}", flush=True)


def play_speech(voice_client: discord.voice.VoiceClient, wav_bytes: bytes) -> None:
    old_player = voice_client._player
    if old_player is not None and voice_client.is_playing():
        # Stop only the player, never via voice_client.stop(): on the pinned
        # py-cord commit that ALSO stops the voice *receive* reader, which
        # silently ends listening until the next "listen on" - the long-
        # chased "packet stall" (caught live 2026-10-02 when a reply cut
        # off one still playing).
        # And wait for the old player thread to actually exit: if a new
        # player starts while it's mid-frame, both drive the voice client's
        # single shared Opus encoder at once, which crashes in native code
        # (access violation) and kills both.
        old_player.stop()
        old_player.join(timeout=1.0)
        voice_client._player = None
    source = discord.FFmpegPCMAudio(io.BytesIO(wav_bytes), pipe=True)
    voice_client.play(source)


async def speak_reply(voice_client: discord.voice.VoiceClient, reply_text: str) -> None:
    """Synthesize and play `reply_text` in `voice_client`.

    Fired via asyncio.create_task(), not awaited, so a slow synthesis (e.g.
    a voice not yet in hf_cache, downloading live) never delays the text
    reply — text always posts on its own schedule regardless of voice.
    """
    speech_text = clean_text_for_speech(reply_text)
    if not speech_text:
        return
    try:
        wav_bytes = await asyncio.to_thread(synthesize_speech_wav, speech_text)
        play_speech(voice_client, wav_bytes)
    except Exception as exc:  # noqa: BLE001 - never let TTS break anything else
        print(f"Voice synthesis/playback failed: {exc}", flush=True)


def get_guild_voice_client(guild: discord.Guild) -> discord.voice.VoiceClient | None:
    return discord.utils.get(discord_client.voice_clients, guild=guild)


async def handle_voice_mode_toggle(message: discord.Message, mode: str, turn_on: bool) -> None:
    """`mode` is "listen" (STT only, gated by STT_ENABLED), "speak" (TTS
    only), or "voice" (both - just speak if STT_ENABLED is False). Each
    dimension is tracked independently per text channel. Connection lifecycle follows whether EITHER is needed -
    joins/stays connected if so, disconnects once both are off."""
    if not message.guild or not isinstance(message.author, discord.Member):
        await message.reply("Voice only works in a server text channel.", mention_author=False)
        return

    channel_id = message.channel.id
    guild_id = message.guild.id

    if mode == "listen" and turn_on and not STT_ENABLED:
        await message.reply(
            "Voice listening (STT) is turned off on this bot — text and "
            "\"speak on\" still work fine.",
            mention_author=False,
        )
        return

    target_speak = turn_on if mode in ("voice", "speak") else None
    # "voice on" quietly skips listening when STT is disabled rather than
    # refusing outright, since speaking alone still works.
    controls_listen = mode == "listen" or (mode == "voice" and (STT_ENABLED or not turn_on))
    target_listen = turn_on if controls_listen else None
    new_listen = channel_listen_enabled.get(channel_id, False) if target_listen is None else target_listen
    new_speak = channel_speak_enabled.get(channel_id, False) if target_speak is None else target_speak

    if not new_listen and not new_speak:
        channel_listen_enabled[channel_id] = False
        channel_speak_enabled[channel_id] = False
        voice_client = get_guild_voice_client(message.guild)
        if voice_client:
            try:
                await voice_client.disconnect(force=True)
            except Exception as exc:  # noqa: BLE001 - still confirm to the user either way
                print(f"Voice disconnect failed: {exc}", flush=True)
        guild_text_targets.pop(guild_id, None)
        await message.reply(f"{mode.capitalize()} off.", mention_author=False)
        return

    author_voice_channel = message.author.voice.channel if message.author.voice else None
    if not author_voice_channel:
        await message.reply(
            f"Join a voice channel first, then mention me with \"{mode} on\".",
            mention_author=False,
        )
        return

    # Check permissions up front: missing View Channel makes the voice
    # handshake hang silently for a full ~30s timeout instead of failing
    # cleanly (discovered live — Connect/Speak can be granted while View
    # Channel isn't, which is enough to make connect() hang either way).
    my_perms = author_voice_channel.permissions_for(message.guild.me)
    missing = [
        name for name, have in (
            ("View Channel", my_perms.view_channel),
            ("Connect", my_perms.connect),
            ("Speak", my_perms.speak),
        ) if not have
    ]
    if missing:
        await message.reply(
            f"I don't have permission to join **{author_voice_channel.name}** "
            f"— missing: {', '.join(missing)}. Ask a server admin to grant "
            "those to my role for this channel.",
            mention_author=False,
        )
        return

    voice_client = get_guild_voice_client(message.guild)
    try:
        if voice_client:
            if voice_client.channel != author_voice_channel:
                await voice_client.move_to(author_voice_channel)
        else:
            voice_client = await author_voice_channel.connect()
    except Exception as exc:  # noqa: BLE001 - report the failure instead of going silent
        print(f"Voice connect failed: {exc}", flush=True)
        await message.reply(
            f"Couldn't connect to voice ({exc}). Discord's voice servers can "
            "get stuck for a bit after an abrupt disconnect — try again in "
            "30-60 seconds.",
            mention_author=False,
        )
        return

    guild_text_targets[guild_id] = channel_id

    if new_listen and not voice_client.is_recording():
        sink = voice_input.WakeWordSink(discord_client.loop, handle_wake_word_utterance)
        voice_client.start_listening(sink)
    elif not new_listen and voice_client.is_recording():
        voice_client.stop_listening()

    channel_listen_enabled[channel_id] = new_listen
    channel_speak_enabled[channel_id] = new_speak

    active = " and ".join(
        label for cond, label in ((new_listen, f'listening for "{WAKE_WORD}"'), (new_speak, "speaking replies"))
        if cond
    )
    await message.reply(f"On in **{author_voice_channel.name}** — {active}.", mention_author=False)


@discord_client.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState,
                                 after: discord.VoiceState):
    # Only care about the bot's own connection being dropped externally
    # (kicked, voice channel deleted, etc.) — reflect that in the toggle
    # state instead of leaving it stuck on with no live connection.
    if member.id != discord_client.user.id:
        return
    if before.channel is not None and after.channel is None:
        guild_id = before.channel.guild.id
        guild_text_targets.pop(guild_id, None)
        for state_dict in (channel_listen_enabled, channel_speak_enabled):
            for channel_id, enabled in list(state_dict.items()):
                if not enabled:
                    continue
                channel = discord_client.get_channel(channel_id)
                if channel and getattr(channel, "guild", None) and channel.guild.id == guild_id:
                    state_dict[channel_id] = False


def run_claude_with_tools(messages: list[dict]):
    """Call Claude with tools enabled, executing any tool_use requests and
    feeding results back, until it produces a final (non-tool-use) response.

    Blocking (the Anthropic call and the Steam HTTP lookups a tool call can
    trigger are both synchronous) — always run via asyncio.to_thread from
    the event loop, never awaited directly.

    `messages` (the channel's persisted history plus the new user turn) is
    only read, never mutated — tool exchanges happen on a local copy, so
    the intermediate tool_use/tool_result turns never get persisted to
    channel_history. Only the original user turn and the final text answer
    do, same as before tools existed.
    """
    working_messages = list(messages)
    response = None
    for _ in range(MAX_TOOL_ITERATIONS):
        tool_modules = active_tool_modules()
        response = anthropic_client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=MAX_TOKENS,
            output_config={"effort": "low"},  # casual chat, not heavy reasoning
            system=build_system_prompt(__version__),
            tools=[t for m in tool_modules for t in m.TOOLS] + [WEB_SEARCH_TOOL],
            messages=working_messages,
        )
        if response.stop_reason == "pause_turn":
            # A long server-side web search paused mid-turn; send the
            # partial turn back as-is and the API picks up where it left off.
            working_messages.append({"role": "assistant", "content": response.content})
            continue
        if response.stop_reason != "tool_use":
            return response

        working_messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result_text = execute_tool_call(block.name, block.input, tool_modules)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_text,
                })
        working_messages.append({"role": "user", "content": tool_results})

    return response  # exceeded MAX_TOOL_ITERATIONS; return whatever we last got


# Discord user ID of the bot application's owner, fetched in on_ready -
# the only account allowed to change wish/bug statuses (see feedback.py).
owner_user_id: int | None = None


def requester_for(user: discord.abc.User | None, name: str | None = None,
                  via: str = "text") -> feedback.Requester:
    if user is None:
        return feedback.Requester(user_id=0, name=name or "Someone", is_owner=False, via=via)
    return feedback.Requester(user_id=user.id, name=name or user.display_name,
                              is_owner=owner_user_id is not None and user.id == owner_user_id,
                              via=via)


async def get_claude_reply(channel_id: int, user_content, requester: feedback.Requester) -> str:
    """Send `user_content` to Claude using `channel_id`'s history, update
    that history in place, and return the reply text (or a ⚠️-prefixed
    error message). Shared by text mentions and wake-word-triggered voice
    utterances - the same conversation, regardless of which path a given
    turn arrived through. `requester` is who sent this turn, for tools
    that need it (wish/bug attribution and owner checks).
    """
    history = channel_history.setdefault(channel_id, [])
    history.append({"role": "user", "content": user_content})
    del history[:-MAX_HISTORY_MESSAGES]

    # to_thread copies the current context, so the tool calls it makes on
    # the worker thread see this requester.
    feedback.current_requester.set(requester)
    try:
        response = await asyncio.to_thread(run_claude_with_tools, history)
        reply_text = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()
        if not reply_text:
            print(f"Empty reply — stop_reason={response.stop_reason!r} "
                  f"content={[(b.type, getattr(b, 'text', None)) for b in response.content]!r}",
                  flush=True)
            reply_text = "(no response)"
    except anthropic.APIError as exc:
        reply_text = f"⚠️ Claude API error: {exc}"
        history.pop()  # don't poison history with a failed turn
    else:
        history.append({"role": "assistant", "content": reply_text})
        history[-2]["content"] = strip_attachments_for_history(user_content)

    return reply_text


async def handle_wake_word_utterance(uid: int, mono_pcm: bytes) -> None:
    """Called by voice_input.WakeWordSink (via run_coroutine_threadsafe,
    off the event loop's own thread) whenever a speaker's utterance ends.
    Transcribes it; utterances that don't contain the wake word are
    silently ignored, same as a text message that doesn't @mention the
    bot. A match gets answered through the same Claude pipeline as text,
    posted to whichever text channel had listening turned on for this
    guild, and spoken back too if speak is also enabled there.
    """

    voice_client = discord.utils.find(lambda vc: vc.is_recording(), discord_client.voice_clients)
    if voice_client is None:
        return
    guild = voice_client.guild
    text_channel_id = guild_text_targets.get(guild.id)
    if text_channel_id is None:
        return
    text_channel = discord_client.get_channel(text_channel_id)
    if text_channel is None:
        return

    try:
        audio = voice_input.mono_pcm_to_whisper_audio(mono_pcm)
        transcript = await asyncio.to_thread(stt_engine.transcribe, audio, "en")
    except Exception as exc:  # noqa: BLE001 - a bad utterance shouldn't kill listening
        print(f"STT transcription failed: {exc}", flush=True)
        return

    query = None
    for wake_word in (WAKE_WORD, *WAKE_WORD_ALIASES):
        query = voice_input.extract_wake_word_query(transcript, wake_word)
        if query is not None:
            break
    now = time.monotonic()
    primed_at = awaiting_voice_query.pop(uid, None)

    if query is None:
        if primed_at is None or now - primed_at > WAKE_WORD_PRIMED_WINDOW_S:
            return
        query = transcript.strip()  # this is the follow-up to an earlier wake-word-only utterance
    elif not query:
        # Wake word said with nothing after it - stay primed for a
        # follow-up utterance instead of answering an empty question.
        awaiting_voice_query[uid] = now
        return

    member = guild.get_member(uid)
    if member is None:
        # Not in the gateway cache (no Members intent) - fetch_member is a
        # direct API call, not cache-dependent, so it works without that
        # privileged intent.
        try:
            member = await guild.fetch_member(uid)
        except discord.HTTPException:
            member = None
    speaker_name = member.display_name if member else "Someone"

    reply_text = await get_claude_reply(text_channel_id, f"{speaker_name} (via voice): {query}",
                                        requester_for(member, speaker_name, via="voice"))
    await text_channel.send(f"🎙️ **{speaker_name}:** {query}\n\n{reply_text}")

    if channel_speak_enabled.get(text_channel_id) and not reply_text.startswith("⚠️"):
        asyncio.create_task(speak_reply(voice_client, reply_text))


@discord_client.event
async def on_ready():
    make_loop_create_task_threadsafe(asyncio.get_running_loop())
    global owner_user_id
    app_info = await discord_client.application_info()
    owner_user_id = app_info.team.owner_id if app_info.team else app_info.owner.id
    print(f"Logged in as {discord_client.user} (id: {discord_client.user.id})", flush=True)
    # Load the TTS model now rather than on the first spoken reply, so its
    # slow cold start doesn't land on someone waiting for an answer.
    # on_ready fires again after every full reconnect; warm up only on the
    # first, since each warm-up stalled the heartbeat ~13s and forced yet
    # another reconnect (seen in the log after network drops, 2026-10).
    global tts_warmed_up
    if not tts_warmed_up:
        tts_warmed_up = True
        asyncio.create_task(asyncio.to_thread(warm_up_tts))


@discord_client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if discord_client.user not in message.mentions:
        return

    content = message.content
    for mention in (f"<@{discord_client.user.id}>", f"<@!{discord_client.user.id}>"):
        content = content.replace(mention, "")
    content = content.strip()

    voice_mode_match = VOICE_MODE_PATTERN.search(content)
    if voice_mode_match:
        await handle_voice_mode_toggle(
            message,
            mode=voice_mode_match.group(1).lower(),
            turn_on=voice_mode_match.group(2).lower() == "on",
        )
        return

    if not content:
        content = "(no message text — just a mention)"

    want_file = bool(FILE_TRIGGER_PATTERN.search(content))
    if want_file:
        content += (
            "\n\n(The chat platform will automatically package this reply as a "
            "downloadable .md file — write the content directly, starting with "
            "a top-level # heading, as clean well-organized Markdown. Don't "
            "mention file/download capabilities or lack thereof; that's "
            "handled outside your response.)"
        )

    # Several people share a channel's history; label the sender the same
    # way voice utterances are ("Name (via voice): ...") so Claude knows
    # who said what. Added after the file-trigger check so a name
    # can't trip it.
    content = f"{message.author.display_name}: {content}"
    user_content = await build_user_content(message, content)

    async with message.channel.typing():
        reply_text = await get_claude_reply(message.channel.id, user_content,
                                            requester_for(message.author))

    if channel_speak_enabled.get(message.channel.id) and not reply_text.startswith("⚠️"):
        voice_client = get_guild_voice_client(message.guild) if message.guild else None
        if voice_client and voice_client.is_connected():
            asyncio.create_task(speak_reply(voice_client, reply_text))

    if want_file and not reply_text.startswith("⚠️"):
        file_bytes = io.BytesIO(reply_text.encode("utf-8"))
        await message.reply(
            "Here you go:",
            file=discord.File(file_bytes, filename=derive_filename(reply_text)),
            mention_author=False,
        )
        return

    for i, chunk in enumerate(chunk_message(reply_text)):
        if i == 0:
            await message.reply(chunk, mention_author=False)
        else:
            await message.channel.send(chunk)


if __name__ == "__main__":
    discord_client.run(DISCORD_BOT_TOKEN)
