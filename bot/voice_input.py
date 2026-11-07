"""Voice input: wake-word listening via a custom py-cord Sink using
webrtcvad for real utterance-boundary detection.

py-cord doesn't expose a native speaking-stop event in the pinned commit
this project depends on for working DAVE voice receive (see bot/README.md's
Voice Input section for why a pinned commit at all) - `Sink.listener()`
doesn't exist yet on that commit. The successful prior community report
that validated this same commit used the same approach: their own
webrtcvad-based utterance detection on top of raw Sink.write() calls, not
a built-in event.

Utterances get transcribed via voxport's WyomingWhisperSTT; only ones
starting with the wake word get handed to the caller (loremaster's
existing Claude chat path).

`write()` is called synchronously from py-cord's own receive thread, not
the event loop - keep it fast, buffer/classify only. Finished utterances
cross back onto the event loop via run_coroutine_threadsafe, same
threading pattern the old (reverted) voice.py used.
"""

import asyncio
import difflib
import logging
import re
import threading
import time

import numpy as np
import webrtcvad
from discord.sinks import Sink

_log = logging.getLogger(__name__)

DISCORD_SAMPLE_RATE = 48000
DISCORD_CHANNELS = 2
DISCORD_SAMPLE_WIDTH = 2  # bytes (16-bit)

WHISPER_SAMPLE_RATE = 16000
RESAMPLE_STEP = DISCORD_SAMPLE_RATE // WHISPER_SAMPLE_RATE

# webrtcvad requires mono 16-bit PCM at 8/16/32/48kHz, in 10/20/30ms frames -
# Discord's 48kHz is directly supported, no resampling needed for VAD itself
# (only for the eventual Whisper handoff).
VAD_FRAME_MS = 30
VAD_FRAME_SAMPLES = DISCORD_SAMPLE_RATE * VAD_FRAME_MS // 1000  # 1440 @ 48kHz/30ms
VAD_FRAME_BYTES = VAD_FRAME_SAMPLES * DISCORD_SAMPLE_WIDTH  # mono bytes per frame
VAD_AGGRESSIVENESS = 2  # 0-3; higher = more aggressive about filtering non-speech

SILENCE_FRAMES_TO_END_UTTERANCE = 25  # ~0.75s of silence @ 30ms/frame
MIN_SPEECH_FRAMES = 15  # ignore short blips (~0.45s) - closing on packet gaps lets
# many tiny noise clips through, which Whisper hallucinates on ("Bye. Bye.")
# and which back up its queue (seen live: STT time climbed to 15s+)

# Safety valve: force-cut an utterance after this many frames even with no
# silence gap. Without this, continuous background noise (a Teams meeting
# in the room, music, etc.) that never gives a clean SILENCE_FRAMES_TO_END_
# UTTERANCE-length gap turns the whole session into one never-ending
# "utterance" that's still open when the listener stops - observed live
# during this project's own testing. Also bounds worst-case latency/cost
# per Whisper call regardless of cause.
MAX_UTTERANCE_FRAMES = 500  # ~15s @ 30ms/frame

# Discord clients stop transmitting when the speaker goes quiet, so a pause
# usually arrives as *no packets at all*, not as silent frames - and the
# frame-based silence check above never sees it. Without this, an utterance
# stays open across pauses until the next speech plus the 15s cap closes it,
# merging separate questions together (observed live). Close an open
# utterance once no audio has arrived from that speaker for this long.
PACKET_GAP_TO_END_UTTERANCE_S = 0.75
PACKET_GAP_CHECK_INTERVAL_S = 0.1


def stereo_bytes_to_mono(pcm_bytes: bytes) -> np.ndarray:
    samples = np.frombuffer(pcm_bytes, dtype=np.int16)
    usable_len = (len(samples) // DISCORD_CHANNELS) * DISCORD_CHANNELS
    samples = samples[:usable_len].reshape(-1, DISCORD_CHANNELS)
    return samples.mean(axis=1).astype(np.int16)


def mono_pcm_to_whisper_audio(mono_pcm: bytes) -> np.ndarray:
    """Crude decimation, matching the old voice.py's approach - adequate
    for wake-word + short-command speech; revisit if transcription quality
    on noisy audio turns out to be a problem."""
    samples = np.frombuffer(mono_pcm, dtype=np.int16).astype(np.float32) / 32768.0
    return samples[::RESAMPLE_STEP]


# How close a word (or short run of words) needs to be to the wake word,
# by character-sequence similarity, to count as a match when it's not an
# exact substring. Chosen from real STT output: "loremaster" transcribed
# as "Laura Master" scores 0.76; unrelated single words scored under 0.67
# in the same check - 0.75 sits in the gap between the two.
WAKE_WORD_FUZZY_THRESHOLD = 0.75

# A fuzzy candidate can be at most this many letters shorter than the wake
# word. Without it, a word that is just the end of the wake word scores
# high: "master" alone scores exactly 0.75 against "loremaster", so
# "Dungeon Master" or "the master bedroom" woke the bot.
WAKE_WORD_MAX_SHORTFALL = 3


def extract_wake_word_query(transcript: str, wake_word: str) -> str | None:
    """Find `wake_word` in `transcript` and return whatever follows it, or
    None if it's not there. Returns "" when the wake word is there with
    nothing after it - main.py then waits for that speaker's next utterance
    as the question. Tries an exact substring match first (cheap,
    handles the common case), then falls back to fuzzy matching a 1-3 word
    window against the wake word - cheap STT models routinely mishear an
    invented word like "loremaster" (e.g. as "Laura Master"), so an exact
    match alone misses real wake-word utterances."""
    lower = transcript.lower()
    idx = lower.find(wake_word.lower())
    if idx != -1:
        return transcript[idx + len(wake_word):].strip(" ,.:!?—-")

    target = wake_word.replace(" ", "").lower()
    word_spans = list(re.finditer(r"[a-zA-Z']+", transcript))
    for window_size in (1, 2, 3):
        for i in range(len(word_spans) - window_size + 1):
            window = word_spans[i:i + window_size]
            candidate = "".join(m.group().lower() for m in window)
            if len(candidate) < len(target) - WAKE_WORD_MAX_SHORTFALL:
                continue
            ratio = difflib.SequenceMatcher(None, candidate, target).ratio()
            if ratio >= WAKE_WORD_FUZZY_THRESHOLD:
                return transcript[window[-1].end():].strip(" ,.:!?—-")
    return None


class _SpeakerState:
    __slots__ = ("frame_buffer", "utterance_pcm", "speech_frames", "silence_run",
                 "in_utterance", "utterance_frame_count", "last_write_at")

    def __init__(self):
        self.frame_buffer = bytearray()  # partial mono PCM, not yet a full VAD frame
        self.utterance_pcm = bytearray()
        self.speech_frames = 0
        self.silence_run = 0
        self.in_utterance = False
        self.utterance_frame_count = 0  # total frames since utterance start, speech+silence
        self.last_write_at = time.monotonic()


class WakeWordSink(Sink):
    """Real-time per-speaker VAD: buffers incoming audio into fixed-size
    frames, classifies each as speech/silence via webrtcvad, and calls
    `on_utterance(user_id, mono_pcm_bytes)` once enough trailing silence
    follows real speech. `mono_pcm_bytes` is 16-bit mono at
    DISCORD_SAMPLE_RATE - pass it through mono_pcm_to_whisper_audio()
    before handing it to an STTEngine.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, on_utterance, *, filters=None):
        super().__init__(filters=filters)
        self.loop = loop
        self.on_utterance = on_utterance
        self.vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)
        self._speakers: dict[int, _SpeakerState] = {}
        # write() runs on py-cord's packet router thread; the gap watchdog
        # runs on its own thread - both touch per-speaker state.
        self._lock = threading.Lock()
        self._stopped = threading.Event()
        threading.Thread(target=self._watch_packet_gaps, name="vad-gap-watchdog",
                         daemon=True).start()

    def write(self, data, user) -> None:
        from discord.voice.packets import VoiceData

        pcm_data = data.pcm if isinstance(data, VoiceData) else data
        uid = getattr(user, "id", user)
        mono = stereo_bytes_to_mono(bytes(pcm_data)).tobytes()

        with self._lock:
            state = self._speakers.setdefault(uid, _SpeakerState())
            state.last_write_at = time.monotonic()
            state.frame_buffer.extend(mono)

            while len(state.frame_buffer) >= VAD_FRAME_BYTES:
                frame = bytes(state.frame_buffer[:VAD_FRAME_BYTES])
                del state.frame_buffer[:VAD_FRAME_BYTES]
                self._process_frame(uid, state, frame)

    def _watch_packet_gaps(self) -> None:
        while not self._stopped.wait(PACKET_GAP_CHECK_INTERVAL_S):
            now = time.monotonic()
            with self._lock:
                for uid, state in self._speakers.items():
                    if state.in_utterance and now - state.last_write_at >= PACKET_GAP_TO_END_UTTERANCE_S:
                        state.frame_buffer.clear()  # partial frame from before the gap
                        self._finish_utterance(uid, state)

    def _process_frame(self, uid, state: _SpeakerState, frame: bytes) -> None:
        is_speech = self.vad.is_speech(frame, DISCORD_SAMPLE_RATE)

        if is_speech:
            state.speech_frames += 1
            state.silence_run = 0
            state.in_utterance = True
            state.utterance_pcm.extend(frame)
        elif state.in_utterance:
            state.silence_run += 1
            state.utterance_pcm.extend(frame)  # keep trailing silence - cuts more naturally
            if state.silence_run >= SILENCE_FRAMES_TO_END_UTTERANCE:
                self._finish_utterance(uid, state)
                return

        if state.in_utterance:
            state.utterance_frame_count += 1
            if state.utterance_frame_count >= MAX_UTTERANCE_FRAMES:
                self._finish_utterance(uid, state)

    def _finish_utterance(self, uid, state: _SpeakerState) -> None:
        pcm = bytes(state.utterance_pcm)
        speech_frames = state.speech_frames
        state.utterance_pcm = bytearray()
        state.speech_frames = 0
        state.silence_run = 0
        state.in_utterance = False
        state.utterance_frame_count = 0

        if speech_frames < MIN_SPEECH_FRAMES:
            return  # too short, likely a noise blip, not real speech

        asyncio.run_coroutine_threadsafe(self.on_utterance(uid, pcm), self.loop)

    def cleanup(self) -> None:
        self._stopped.set()
        with self._lock:
            self._speakers.clear()
