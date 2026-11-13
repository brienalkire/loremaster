# Changelog

All notable changes to this project are documented here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/).
This project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.7.1] - 2026-11-13

### Fixed
- Asked what version it's running or what's new, the bot now describes
  its latest release. It used to read the empty "Unreleased" section of
  CHANGELOG.md, so it could give the version number but not the changes.

### Added
- A narrated video introduction to Loremaster, made with podcast-generator
  and attached to the release. Its slides, script and pronunciation
  lexicon are in `examples/briefing/`.

## [0.7.0] - 2026-11-09

### Added
- Dice rolls: "roll 1d20", "roll 3d6", "roll 2d6+3", or "roll 1d20 each
  for Alice, Bob and Cara" (`roll_dice`, `bot/dice.py`). The numbers come
  from the operating system's random source, never from the model. For
  several people, the bot says who rolled highest, including ties.

## [0.6.0] - 2026-11-07

First public release. Each group runs its own copy, with its own Discord
bot and Anthropic API key. See README.md to get started. Entries before
this one come from the private development history; the instruction
files and campaigns they mention belong to the original group and
aren't included.

### Added
- A home folder for each group's data, separate from the code: set
  `LOREMASTER_HOME`, or leave it unset to use the clone folder. `.env`,
  `instructions/`, the database, backups and logs live there. See
  `bot/paths.py` and MANUAL.md.
- Settings in `.env` for things that used to be fixed in `main.py`:
  `LOREMASTER_TTS_VOICE`, `LOREMASTER_WAKE_WORD`,
  `LOREMASTER_WAKE_WORD_ALIASES`, `LOREMASTER_VOICE_INPUT`, `WHISPER_HOST`
  and `WHISPER_PORT`.
- Tool plugins (`bot/plugins/`). A game extension turns one on in its
  `plugins.txt`, and its tools are offered only while that game's campaign
  is active.
- `bot/core_instructions.md`: tool-usage rules that apply under every
  persona, so a persona only has to describe the bot and the group.
- A generic example persona and game extension in `examples/instructions/`,
  used when the home folder has no `instructions/`.
- Tests (`tests/`, run with `python -m pytest`) for campaign memory,
  feedback, the system prompt and plugins, the home folder and settings,
  backups, message handling and wake-word matching, and a GitHub Actions
  CI workflow that runs them with a lint check on Linux and Windows.
  `prompt.py` and `text_utils.py` hold code moved out of `main.py` so it
  can be tested without starting the bot.
- MANUAL.md (setup from scratch, configuration, voice, backups, costs,
  privacy, troubleshooting) and an MIT LICENSE. README.md,
  HOW_TO_TALK_TO_LOREMASTER.md and bot/README.md are rewritten for any
  group.
- The desktop control panel has an "About" menu that shows the bot's
  version and author.
- The owner can send a wish or bug to the developer: "send bug 4
  upstream" replies with a link to a pre-filled GitHub issue
  (`send_feedback_upstream`). It leaves out who reported or backed the
  item, and nothing is sent until the owner submits it.
- GitHub issue forms for bug reports and feature ideas.

### Changed
- **Voice input is now off by default.** Set `LOREMASTER_VOICE_INPUT=true`
  in `.env` to keep it.
- **`GAME_EXTENSION` now defaults to blank** instead of `enshrouded`.
- "Warmaster" is a default wake-word alias for "loremaster", because
  Whisper often hears it that way. Setting `LOREMASTER_WAKE_WORD_ALIASES`
  replaces the default, and a custom wake word gets no default alias.
- The manual suggests naming the bot "Loremaster", explains that the wake
  word doesn't follow the bot's Discord name, and gives advice on picking
  a custom wake word.
- `enshrouded_lookup` is now a plugin. To keep its tools, an Enshrouded
  extension needs `enshrouded_lookup` in its `plugins.txt`.
- The persona file can be named `persona.md`.
  `instructions_gameassistant_base.md` still works.
- An install that already has `bot/loremaster.db` keeps its database,
  backup and log in `bot/`.
- The control panel runs the bot with its own Python environment, and only
  offers to commit a backup when the backup files are in a git repository.
- Depends on `voxport`, the renamed `vox_bridge` toolkit, now installed
  from PyPI (`voxport[all]>=0.5.0,<0.6` in `requirements.txt`) instead
  of an editable sibling checkout. To update an existing venv, from
  `bot/`: `pip uninstall vox_bridge voxport`, then
  `pip install -r requirements.txt`. `soundfile` is now listed
  directly, since voxport no longer pulls it in.
- voxport 0.5.0 logs Kokoro progress instead of printing it; the bot
  turns that logging on, so "Loading Kokoro model..." and "Generating
  audio..." lines still appear in the log (per-segment lines no longer
  do).

### Fixed
- Saying only the wake word and then pausing ("Loremaster..." then the
  question) now works as intended. The bot waits up to 8 seconds for that
  speaker's question. Before, it ignored the pause and the question that
  followed, because the wake-word check returned "no wake word" instead of
  "wake word with nothing after it".
- Words that are just the end of the wake word no longer wake the bot.
  "master" alone scored as a match for "loremaster", so "Dungeon Master"
  or "the master bedroom" in voice chat woke it.
- Three py-cord `DeprecationWarning`s at startup: voice-client type
  hints now use `discord.voice.VoiceClient` instead of the deprecated
  `discord.VoiceClient` alias (same class).

## [0.5.4] - 2026-10-31

### Changed
- Every line in the bot log now starts with a date and time (`10-31
  13:02:41 ...`), covering prints, warnings, logging output and
  tracebacks, so log errors can be matched to real events.
- Gateway reconnects log one line with the cause (e.g. `Attempting a
  reconnect in 8.77s (ClientConnectorDNSError: ...)`) instead of a
  ~60-line traceback. These were all routine network drops (PC asleep,
  Wi-Fi blips) that the bot recovered from on its own, but they read
  like crashes. Other errors keep their full tracebacks.

### Fixed
- The TTS warm-up re-ran after every full reconnect, not just at
  startup. Each warm-up stalled the Discord heartbeat ~13s
  ("Can't keep up ... websocket is 13s behind") and forced another
  reconnect. It now runs once per bot start.

## [0.5.3] - 2026-10-11

### Added
- An Enshrouded 1.0 necromancer leveling guide for the group's own
  extension.

### Removed
- Leftover `[latency]` debug logging from the voice-input investigation
  (per-utterance STT/Claude/send timings, packet `write()` counts, and the
  voice endpoint IP). Voice has been stable since 0.3.3, so the bot log is
  now much quieter while listening.

### Fixed
- Spoken replies stalling for minutes when several arrived together right
  after a restart, especially with a game running on the same GPU: each
  reply loaded its own copy of the Kokoro voice model at once. Speech now
  synthesizes one reply at a time, and the model loads at startup instead
  of on the first spoken reply.

## [0.5.2] - 2026-10-11

### Changed
- **Loremaster now knows who's typing** (wish #3). Typed messages reach
  Claude labeled with the sender's Discord display name, matching how
  voice utterances were already labeled, so in a shared channel it can
  tell who asked what instead of assuming everything is from one person.

## [0.5.1] - 2026-10-04

### Added
- **Web search** (wish #2): loremaster can now search the web for things
  its training data can't know - patch notes, update changes, game news.
  Uses Anthropic's server-side web search tool (no extra API key), capped
  at 3 searches per reply; the system prompt steers it toward the
  dedicated Steam/Shrouded Tools/memory tools first and away from reading
  URLs aloud. Long searches that pause mid-turn (`pause_turn`) are resumed
  instead of returning a half-finished reply.

## [0.5.0] - 2026-10-02

### Added
- **Wish list and bug reports** for loremaster itself (`bot/feedback.py`).
  Anyone in the group can add a feature wish or report a bug in natural
  language, typed or by voice, or back an existing item; bug reports also
  record the bot version, text vs. voice, and what went wrong. Only the
  bot application's owner can mark items done/fixed/declined or remove
  them, checked in code against the real Discord account. `export_db.py`
  now also writes `WISHLIST.md` and `BUGS.md`.
- Desktop control panel (`bot/control_panel.py`, shortcut via
  `bot/make_shortcut.ps1`): start/stop the bot, watch its recent
  activity, and **Back up** (export, then optionally commit + push just
  the backup files) without opening a terminal. The bot runs as its own background
  process, so closing the panel leaves it running.

### Changed
- Tools now know which Discord account sent each message (typed or
  spoken), so wishes and bug reports are attributed correctly.

## [0.4.2] - 2026-10-02

### Added
- `bot/export_db.py` — backs up campaign memory (`loremaster.db`) as a
  readable, diffable SQL dump (`loremaster_backup.sql`, committed), and
  restores from it with `--restore`. The live `.db` is now gitignored.

## [0.4.1] - 2026-10-02

### Changed
- "voice on"/"voice off" now control both listening and speaking;
  "listen on" and "speak on" each still control just one. (Previously
  "voice" was an alias for "speak" only.) With STT disabled, "voice on"
  just enables speaking.

## [0.4.0] - 2026-10-02

### Changed
- **Voice input (STT) is now on by default** (`STT_ENABLED = True`) — say
  "listen on" in a mention while in a voice channel, then "loremaster" +
  a question. With the 0.3.2/0.3.3 fixes it held up in live testing, so
  it's going into real campaign use to shake out any remaining bugs.
  "voice on" still only enables spoken replies; listening stays its own
  explicit toggle. Set `STT_ENABLED = False` to turn it back off.

## [0.3.3] - 2026-10-02

### Fixed
- **Root cause of the voice-input "packet stalls"** (multi-minute
  stretches where the bot heard nothing, then recovered with no error).
  Not a network problem: on the pinned py-cord commit,
  `VoiceClient.stop()` also stops the voice *receive* reader, so a spoken
  reply interrupting another silently ended listening until the next
  "listen on". Playback is now stopped via the player thread only.
  Verified live: a question asked after one reply interrupted another
  was heard and answered.
- Short noise clips no longer reach Whisper (minimum speech raised from
  ~0.15s to ~0.45s) — with packet-gap closing they were frequent, got
  hallucinated transcripts ("Bye. Bye."), and backed STT up to 15s+.

### Changed
- `bot/README.md`'s Voice Input section rewritten: the stall is no longer
  described as an unresolved network issue. STT remains off by default
  (`STT_ENABLED = False`) pending longer real-session testing.

## [0.3.2] - 2026-10-02

### Fixed
Voice-input fixes found in live testing (STT still ships disabled pending
more testing):
- ~5s delay before every received voice packet was processed. py-cord's
  socket reader thread schedules packets with a non-thread-safe
  `loop.create_task()` that never wakes the event loop; the loop is now
  woken after any off-thread `create_task` (measured live: ~4.8s → ~1ms).
- Separate spoken questions merged into one 15s clip. Discord stops
  sending packets during pauses, so frame-based silence detection never
  fired; an utterance now also closes after 0.75s with no packets.
- Spoken replies crashed (Opus encoder access violation, both replies
  silent) when two finished synthesis together — playback now waits for
  the previous player thread to exit before starting.
- Audio from a speaker silently discarded after an RTP sequence jump —
  the jitter buffer now resyncs after a run of "old" drops.

### Added
- "Warmaster" accepted as a wake word (a recurring Whisper mishearing
  that scored just under the fuzzy-match threshold).

## [0.3.1] - 2026-09-27

### Added
- Claude can now read `.md`/`.txt` file attachments on a mention, not
  just images — e.g. bring back a previous "as a file" export and ask
  for changes. Capped at 50,000 characters; folded in for that turn only
  (same one-turn-then-stripped pattern already used for images, so it
  doesn't balloon channel history on later turns).

## [0.3.0] - 2026-09-24

### Added
- Real-time voice input (STT) — join a voice channel, say "loremaster"
  followed by a question, get answered without typing. Built as
  `bot/voice_input.py`'s `WakeWordSink`: per-speaker `webrtcvad`
  utterance segmentation (closes on ~0.75s silence or a 15s safety cap),
  transcribed via `vox_bridge`'s `WyomingWhisperSTT` against a local
  Wyoming Whisper container. Fuzzy wake-word matching tolerates STT
  mishearings of "loremaster" (e.g. "Laura Master"); a wake-word-only
  utterance primes the next utterance (8s window) as the query, handling
  the natural "Loremaster," *pause*, "question" speech pattern.
  **Currently disabled** (`STT_ENABLED = False`) pending a fix for an
  intermittent Discord voice packet-delivery issue found in live testing
  — see `bot/README.md`'s "Voice Input (STT)" section for the full story.
- Independent `listen on/off` and `speak on/off` toggles alongside the
  existing `voice on/off` (which now controls speak/TTS only, so it can't
  accidentally enable the currently-disabled STT feature).
- Migrated the real bot from `discord.py` to a pinned commit of an
  unmerged py-cord PR (`Pycord-Development/pycord#3159`) — required for
  DAVE-encrypted voice *receive* at all, which is broken in every
  released version of both libraries. TTS voice output re-verified
  working after the swap.

## [0.2.0] - 2026-09-24

### Added
- Persistent campaign memory (`bot/memory_store.py`), backed by a small
  SQLite database: campaigns can be listed, created, and switched live via
  chat, replacing the old `GAME_EXTENSION`-env-var-plus-restart workflow.
  Each campaign holds a rewritable current-state doc (party/character
  status, objective, gear) and a short event log; there's also a general
  memory layer for cross-campaign facts. Migrated the Enshrouded and
  Rogue Trader character sheets out of static instruction files and into
  the first campaigns.
  Battle-tested in live group use for several days before this release.
- `lookup_steam_game` Claude tool for live Steam store data (price/sale
  status, multiplayer/co-op tags, release date, Early Access status,
  metacritic score, current player count) — for anything newer than
  training-data knowledge.
- `lookup_enshrouded_item`/`lookup_enshrouded_recipe` Claude tools
  (`bot/enshrouded_lookup.py`) for factual Enshrouded item stats and
  crafting/cooking/upgrade recipes, via the community-run Shrouded Tools
  database (shrouded.tools) — static per-game-version data, fetched once
  and cached in memory rather than re-fetched per query.
- The bot now knows its own version and recent changes: ask "what version
  are you running" or "what's new" and it answers from this changelog's
  latest entry instead of a bare version number.
- Default to short replies unless the group asks for depth (a quick
  question gets a quick answer, not a full structured writeup) — also
  reduces voice-reply synthesis/playback time.
- `HOW_TO_TALK_TO_LOREMASTER.md`: a group-facing cheat sheet for the
  bot's mention phrases and toggles.
- Documented optional GPU acceleration for voice synthesis (CUDA build of
  `torch` — ~19x faster warm synthesis on a compatible NVIDIA GPU).

### Fixed
- Hardened `update_campaign_state`/`remember_general` against silent data
  loss: a live incident showed Claude eliding unchanged content with a
  placeholder (e.g. `[...unchanged...]`) instead of copying it back
  verbatim, which is a full overwrite, not a diff — the placeholder
  became the permanently stored content. Both tools now reject a rewrite
  that comes back much shorter than the current notes unless explicitly
  confirmed (`confirm_shrink=true`), and their descriptions plus the base
  instructions spell out the verbatim-copy requirement explicitly.

## [0.1.0] - 2026-09-19

### Added
- Discord bot core: relays `@mention`s to Claude, holds per-channel
  in-memory conversation history, responds only when mentioned.
- Game-specific system prompt extensions (Enshrouded, Rogue Trader) layered
  on a base game-assistant prompt.
- File-export trigger ("as a file" / "to download") to get a reply back as
  a downloadable `.md` attachment.
- Image attachment support (e.g. character-sheet screenshots) as vision
  input to Claude.
- Voice output: a `voice on`/`voice off` mention toggle joins/leaves the
  author's current voice channel and speaks replies aloud via
  `vox_bridge`'s `KokoroDirectTTS`, run off the event loop with
  `asyncio.to_thread`/`asyncio.create_task` so it never delays the text
  reply. Requires `discord.py[voice]` (PyNaCl + davey) and `ffmpeg`.
- Loremaster persona: a learned, faintly theatrical, occasionally snooty
  sage voice layered over the previously purely-functional interaction
  style, sized for text-to-speech as well as chat.
- Up-front voice-channel permission checks (View Channel, Connect, Speak)
  so a missing permission fails immediately with a specific message
  instead of a silent ~30s connection timeout.

### Fixed
- discord.py 2.7 requires the separate `davey` package to connect to voice
  at all (not just for end-to-end encryption) — `PyNaCl` alone, the old
  requirement, is no longer sufficient.
- Voice connect/disconnect failures previously propagated as unhandled
  exceptions with no reply at all; now reported back to the channel.
