# bot/ – developer notes

To set up and run the bot, see [../MANUAL.md](../MANUAL.md). This file is
for working on the code.

## Tests

From the clone folder, with the bot's virtual environment active:

```
python -m pip install -r requirements-dev.txt
python -m pytest
python -m pyflakes bot/*.py bot/plugins tests
```

The tests never import `main.py`, which connects to Discord and loads the
speech model. Code worth testing lives in modules that can be imported on
their own. They use a temporary home folder and database, never your real
ones. CI (`.github/workflows/ci.yml`) runs the same steps on Linux and
Windows, installing only what the tests import.

## Modules

| File | What it does |
| --- | --- |
| `main.py` | Discord client, Claude calls and the tool loop, attachments, voice toggles, wake-word handling. Also patches several py-cord voice-receive bugs at import time (see below). |
| `paths.py` | Finds the home folder (`LOREMASTER_HOME`), loads its `.env`, and has helpers for reading settings. Import it before anything reads a setting. |
| `prompt.py` | Builds the system prompt and picks the tool set (core tools plus the active extension's plugins) for each Claude call. |
| `text_utils.py` | Message patterns ("voice on", file requests), attachment markers, splitting long replies, cleaning text for speech. |
| `core_instructions.md` | Tool-usage rules sent before every persona. |
| `memory_store.py` | SQLite campaign memory (campaigns, current state, event log, general memory), exposed as Claude tools. |
| `feedback.py` | Wish list and bug reports in the same database. The owner check uses the real Discord account and doesn't trust Claude. |
| `steam_lookup.py` | Live Steam storefront data. No API key needed. |
| `dice.py` | Dice rolls in NdK notation from `secrets.SystemRandom`, so results never come from the model. |
| `plugins/` | Optional per-game tools, turned on by an extension's `plugins.txt`. `enshrouded_lookup.py` is the example. |
| `voice_input.py` | `WakeWordSink`: per-speaker buffering, VAD segmentation, wake-word matching. |
| `export_db.py` | Database to SQL backup and back again, plus the WISHLIST/BUGS exports. |
| `control_panel.py` | Windows tkinter start/stop/backup panel. `make_shortcut.ps1` makes its shortcut. |

### Tools

Every tool module has the same shape: a `TOOLS` list of Anthropic tool
definitions and `execute_tool(name, tool_input) -> str` returning JSON
text. `main.active_tool_modules()` decides the tool set on every Claude
call: the core modules plus the active extension's plugins. That's why
`switch_campaign` changes the tool set without a restart. A plugin can also
set an `INSTRUCTIONS` string, which is added to the system prompt while
the plugin is active.

Web search is Anthropic's server-side `web_search` tool. It runs during
`messages.create` and never reaches `execute_tool`.

### System prompt

`build_system_prompt()` runs on every call, so edits to instruction files
take effect on the next reply. It joins these parts: core instructions,
persona, version and latest changelog section, extension instructions,
`project_files/*.md`, plugin instructions, campaign memory, and general
memory.

### Version

`__version__` in `main.py` is the version. Keep it in step with
`CHANGELOG.md` and the git tag. The control panel reads it from the
source file without importing `main.py`.

## Voice Input (STT)

Voice input (`voice_input.WakeWordSink`) is experimental and off unless
`LOREMASTER_VOICE_INPUT=true`.

### Why a pinned py-cord commit

Released `discord.py` and released py-cord can't receive voice audio on
DAVE-encrypted channels, and Discord now uses DAVE for voice. The fix only
exists in an unmerged, comment-locked pull request
(`Pycord-Development/pycord#3159`). Several independent projects have
tested their own recording and STT bots against it. `requirements.txt`
pins the exact commit (`05cf65f`) instead of following the branch, which
limits the risk of depending on unreleased code without removing it.
There's no upstream support if it breaks.

py-cord and discord.py both install as the `discord` package, so they
can't be installed together. py-cord replaces discord.py here.

The pin is also why loremaster isn't on PyPI: PyPI rejects direct git
dependencies.

### Patches to the pinned commit

`main.py` patches these bugs at import time, before any voice connection:

- The socket reader thread schedules packets with a `loop.create_task()`
  that isn't thread-safe and never wakes the event loop. That caused about
  5 seconds of lag on every packet.
- The jitter buffer never resyncs after a jump in the RTP sequence number,
  so it silently drops that speaker's audio until the 16-bit counter wraps.
- `UDPKeepAlive` defaults to a 5000-second delay
  (`Pycord-Development/pycord#3388`), so receive drops after 5 to 9 minutes.
- `VoiceClient.stop()`, which is meant to stop *playback*, also stops the
  *receive* reader. So a spoken reply that interrupted another silently
  ended listening. This caused the long "packet stall" hunt that ended in
  0.3.3. `play_speech` now stops only the player thread.
- Two players starting at once crashed the shared Opus encoder, so
  `play_speech` waits for the old player thread to exit.

### How it works

- `WakeWordSink` buffers each speaker's audio and uses `webrtcvad` to split
  it into utterances. The pinned commit has no event for when someone stops
  speaking.
- An utterance ends after about 0.75 seconds of silence, or about 0.75
  seconds with no packets. Discord clients stop sending during pauses, so
  silence usually shows up as missing packets rather than silent frames.
- An utterance is cut off at 15 seconds regardless, which bounds the
  delay and copes with background noise that never goes quiet.
- Utterances with less than about 0.45 seconds of speech are dropped as
  noise. Whisper makes things up from them, and they back up its queue.
- Utterances go to a Wyoming Whisper server through voxport's
  `WyomingWhisperSTT`.
- Wake-word matching tries an exact substring first, then fuzzy matching
  (`difflib`, a window of 1 to 3 words, threshold 0.75). This catches
  mishearings of an invented word like "loremaster", such as "Laura
  Master" (0.76) or "Ormaster" (0.89). A candidate more than 3 letters
  shorter than the wake word never matches, because "master" alone scores
  0.75. Near-misses just below the threshold, such as "Warmaster" or
  "Lawmaster" (both 0.74), need an alias. "Warmaster" is a default alias
  for "loremaster" (`voice_input.DEFAULT_WAKE_WORD_ALIASES`); others go in
  `LOREMASTER_WAKE_WORD_ALIASES`, which replaces the default. Real words
  close to the wake word still match: "remaster" scores 0.89.
- An utterance that's only the wake word "primes" that speaker's next
  utterance, within 8 seconds, to count as the question. People often
  pause after the wake word, and VAD splits that into two utterances.

### Known issues

- Saying a real word that's close to the wake word ("remaster") wakes
  the bot.

- Without headphones or echo cancellation, a speaker's microphone picks up
  the bot's replies. They're ignored because they don't contain the wake
  word, but they still use Whisper time.
- If listening stops, look in the log for a py-cord `Socket reader ... is
  waiting to be set as running` warning in the middle of a session. That
  means receive stopped. Check for it before suspecting the network.
- A busy CPU slows Whisper. `docker stats` shows whether that's happening.
