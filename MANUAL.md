# Loremaster Manual

This manual takes you from nothing to a running bot, then covers
configuration, personas, voice, backups, privacy, and troubleshooting. For
a short overview, see [README.md](README.md).

- [Setup](#setup)
- [Configuration](#configuration)
- [Persona and game extensions](#persona-and-game-extensions)
- [Using the bot](#using-the-bot)
- [Voice](#voice)
- [Backups](#backups)
- [Running it all the time](#running-it-all-the-time)
- [Costs](#costs)
- [Privacy: what's stored and what you should tell your group](#privacy-whats-stored-and-what-you-should-tell-your-group)
- [Upgrading](#upgrading)
- [Troubleshooting](#troubleshooting)

---

## Setup

### Requirements

- **Python 3.12** (the tested version).
- **Git**, because `requirements.txt` installs py-cord from GitHub.
- **ffmpeg** on your `PATH`, only if you want spoken replies. On Windows,
  `winget install ffmpeg` is the quickest way.
- About 2 GB of disk for the Python packages and the speech model.
- A Discord account with permission to add bots to your server ("Manage
  Server"), or a friend who has it.
- An Anthropic account with API credit.

### 1. Create the Discord bot

1. Open the [Discord Developer Portal](https://discord.com/developers/applications)
   and click **New Application**. The name you choose is the bot's name in
   your server, and what people type after `@`. "Loremaster" is a good
   choice. The voice wake word doesn't follow this name: it stays
   "loremaster" unless you change `LOREMASTER_WAKE_WORD` (see
   [Voice input](#voice-input-experimental)).
2. Open **Bot** in the sidebar.
   - Click **Reset Token**, then copy the token. This is your
     `DISCORD_BOT_TOKEN`. Treat it like a password: anyone with it can
     control your bot.
   - Under **Privileged Gateway Intents**, turn on **Message Content
     Intent**. Without it, the bot can't read what people write to it.
   - Optional: turn off **Public Bot**, so only you can invite it to
     servers.
3. Optional: set an avatar under **General Information**.
   `bot/assets/icon.png` is one you can use.

Whoever owns this Discord application is the bot's **owner**. Only the
owner can change the status of wish-list items and bug reports.

### 2. Get an Anthropic API key

1. Sign in at [console.anthropic.com](https://console.anthropic.com/).
2. Add credit under **Billing**. Consider setting a monthly spend limit
   there too (see [Costs](#costs)).
3. Create a key under **Settings > API Keys**. This is your
   `ANTHROPIC_API_KEY`.

### 3. Install

From a terminal:

```
git clone https://github.com/brienalkire/loremaster.git
cd loremaster\bot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

On Linux or macOS, use `source .venv/bin/activate` instead.

Then make your `.env` file and fill in the two required values:

```
copy ..\.env.example ..\.env
notepad ..\.env
```

The first start downloads the Kokoro speech model (about 330 MB) and a
small spaCy language model, so it's slow. Later starts are quicker.

### 4. Invite the bot to your server

1. In the Developer Portal, open **OAuth2 > URL Generator**.
2. Under **Scopes**, tick `bot`.
3. Under **Bot Permissions**, tick:
   - **View Channels**
   - **Send Messages**
   - **Read Message History**
   - **Attach Files** (for replies sent as files)
   - **Connect** and **Speak** (for voice)
4. Open the generated URL and choose your server. You need "Manage Server"
   on that server. If you don't have it, send the URL to someone who does.

Even with these permissions, a single voice channel can deny the bot
**View Channel** in its own permission settings, and then the bot can't
join it. If that happens, the bot tells you what's missing.

### 5. Start it

From `bot\` with the virtual environment active:

```
python main.py
```

When it's ready, it prints `Logged in as ...`. Mention it in a channel:
`@YourBot hello`.

Or use the **desktop control panel** (Windows only). It starts and stops
the bot in the background, shows the latest log lines, and backs up its
memory. To create a desktop shortcut for it:

```
powershell -ExecutionPolicy Bypass -File make_shortcut.ps1
```

Closing the control panel window leaves the bot running. Reopening it
finds the running bot again.

---

## Configuration

### The home folder

Everything that belongs to your group lives in one **home folder**:

| File | What it is |
| --- | --- |
| `.env` | Your token, API key and settings |
| `instructions/` | Your persona and game extensions |
| `loremaster.db` | Campaign memory, wish list and bug reports |
| `loremaster_backup.sql` | A text backup of the database |
| `WISHLIST.md`, `BUGS.md` | Readable copies of the feedback |
| `loremaster.log` | Bot output, when started from the control panel |

By default the home folder is the folder you cloned. To keep your data
somewhere else, for example so the code folder can be replaced freely, set
the `LOREMASTER_HOME` environment variable to another folder and move your
`.env` there:

```
setx LOREMASTER_HOME "%USERPROFILE%\Documents\loremaster"
```

`setx` takes effect in new terminals, not the current one.

### Settings in `.env`

| Setting | Default | What it does |
| --- | --- | --- |
| `DISCORD_BOT_TOKEN` | (required) | The bot's Discord token |
| `ANTHROPIC_API_KEY` | (required) | Your Anthropic API key |
| `CLAUDE_MODEL` | see `bot/main.py` | Which Claude model answers |
| `GAME_EXTENSION` | blank | Extension to use before any campaign exists |
| `LOREMASTER_TTS_VOICE` | `bm_george` | Kokoro voice for spoken replies |
| `LOREMASTER_VOICE_INPUT` | `false` | Turn on voice input (experimental) |
| `WHISPER_HOST`, `WHISPER_PORT` | `localhost`, `10300` | Speech-to-text server for voice input |
| `LOREMASTER_WAKE_WORD` | `loremaster` | Word that wakes the bot in voice |
| `LOREMASTER_WAKE_WORD_ALIASES` | `warmaster` for the default wake word, none otherwise | Extra spellings of the wake word, comma-separated. Setting it replaces the default. |

Restart the bot after changing `.env`. Real environment variables take
priority over `.env` values.

---

## Persona and game extensions

The bot's instructions are built from these parts, in order:

1. **Core instructions** (`bot/core_instructions.md`), which come with the
   code. They tell it how to use its tools: memory, Steam, web search and
   feedback. You don't need to change them.
2. **Your persona** (`instructions/persona.md`): who the bot is, who's in
   your group, and what you like to play.
3. **The active game extension** (`instructions/<game>/`), if a campaign
   is active.
4. **Campaign memory** for the active campaign, and general memory.

All of this is sent to Claude with every reply. Bigger files cost more per
reply, so keep them focused.

### Write your persona

Until your home folder has an `instructions/` folder, the bot uses the
examples in `examples/instructions/`. To start your own, copy them into
the home folder. From the clone folder, when that's also your home folder:

```
xcopy /E /I examples\instructions instructions
```

Then edit `instructions/persona.md`:

- List your group members, with handles close to their Discord display
  names, so the bot can tell who's talking.
- Describe your schedule, what you like to play, and what to avoid.
- Change the personality if you like. The example is a slightly snooty
  sage.

Don't put anything in it your group wouldn't want sent to Anthropic.

### Add a game extension

A game extension is a folder under `instructions/`, named for the game, for
example `instructions/valheim/`:

```
instructions/valheim/
  instructions_valheim_rag.md   main instructions for this game
  project_files/                optional extra notes, all *.md loaded
  plugins.txt                   optional tool plugins to turn on
```

`examples/instructions/example_game/` is a template. Then ask the bot to
start a campaign: `@YourBot start a new Valheim campaign called "Viking
Tuesdays"`. The bot only accepts a game name that has a folder.

Only put text you wrote, or have the right to use, in `project_files/`.
Copying wiki pages or community guides there can break their licences.

### Switch campaigns

Only one campaign is active at a time. Ask the bot to list, create or
switch campaigns. Switching changes the game extension straight away, with
no restart.

### Tool plugins

A plugin gives the bot extra tools for one game. An extension turns one on
by listing its module name in `plugins.txt`. The only plugin included is
`enshrouded_lookup`, which looks up Enshrouded items and recipes from the
community site [Shrouded Tools](https://shrouded.tools/). To write your
own, see `bot/plugins/__init__.py`.

---

## Using the bot

[HOW_TO_TALK_TO_LOREMASTER.md](HOW_TO_TALK_TO_LOREMASTER.md) is a short
guide you can share with your group. In brief:

- **Ask anything** by mentioning the bot. Replies are short unless you ask
  for detail.
- **Get a file:** include "file", "download" or "markdown" and the reply
  comes back as a `.md` attachment.
- **Share images or files:** attach a screenshot, or a `.md` or `.txt`
  file (up to 50,000 characters).
- **Campaigns:** "start a campaign", "switch to our Rogue Trader
  campaign", "remember that we beat the dragon".
- **Feedback:** "I wish you could...", "that's a bug". "What's on the
  wish list?" lists open items. See
  [Wish list and bug reports](#wish-list-and-bug-reports).
- **Voice:** "speak on/off", "listen on/off", "voice on/off" (see
  [Voice](#voice)).

Conversation history is kept per channel, in memory only, and is lost when
the bot restarts. Campaign memory is saved to the database.

### Wish list and bug reports

Anyone in your server can tell the bot what they wish it could do, or
what it got wrong. Those items stay in your copy: in `loremaster.db`, and
in `WISHLIST.md` and `BUGS.md` after a backup. You're the owner (whoever
created the Discord application), so only you can mark items done, fixed
or declined, or remove them:

```
@Loremaster mark bug 4 fixed
@Loremaster decline wish 2, we don't need it
```

**Sending feedback to the developer.** Nothing goes to Loremaster's
developer automatically. To pass an item on, ask:

```
@Loremaster send bug 4 upstream
```

The bot replies with a link that opens a new
[GitHub issue](https://github.com/brienalkire/loremaster/issues), already
filled in with the item's summary, details, and the bot version. It
leaves out who reported or backed it. Before you click **Submit**, read
it and remove anything private, such as names or campaign details.
You need a GitHub account. You can also open an issue yourself from the
same page.

---

## Voice

Voice commands go in a mention while you're in a voice channel. The bot
joins your channel. Text replies keep posting either way.

| Command | What it does |
| --- | --- |
| `speak on` / `speak off` | Speak replies aloud |
| `listen on` / `listen off` | Listen for the wake word (voice input) |
| `voice on` / `voice off` | Speak. Also listen, if voice input is turned on |

The settings last per text channel until turned off. The bot leaves the
voice channel when both are off.

### Spoken replies

Spoken replies need ffmpeg on your `PATH`. Speech uses the Kokoro model and
runs on your CPU, which takes a few seconds per reply. To choose another
voice, set `LOREMASTER_TTS_VOICE` (see voxport's README for the list).

**Optional speed-up with an NVIDIA GPU.** The default PyTorch install runs
on the CPU only. Installing a CUDA build of PyTorch can make speech many
times faster:

```
pip show torch
pip install torch==<that version> --index-url https://download.pytorch.org/whl/cu130 --force-reinstall --no-deps
```

Choose a CUDA tag (`cu130` here) that your GPU driver supports. Check the
header of `nvidia-smi`. Without a compatible GPU, skip this.

### Voice input (experimental)

With voice input, people in the voice channel say the wake word and then a
question, and the bot answers without anyone typing.

> **Listening records people.** Everything said in the channel while the
> bot listens is sent to your speech-to-text server, and the questions
> that follow the wake word are sent to Anthropic. Tell everyone in your
> server before you turn it on, and see
> [Privacy](#privacy-whats-stored-and-what-you-should-tell-your-group).

To turn it on:

1. Run a [Wyoming](https://github.com/rhasspy/wyoming) Whisper server. The
   easiest way is Docker:

   ```
   docker run -d --name whisper -p 10300:10300 rhasspy/wyoming-whisper --model base.en --language en
   ```

   The image is `rhasspy/wyoming-whisper`, not `wyoming-faster-whisper`.

2. Set `LOREMASTER_VOICE_INPUT=true` in `.env`. Also set `WHISPER_HOST` if
   the server runs on another machine.
3. Restart the bot, join a voice channel, and say `@YourBot listen on`.
4. Say "Loremaster, what should we play next?"

Tips:

- Use headphones, or Discord's echo cancellation, so the bot doesn't hear
  its own replies.
- If Whisper keeps hearing the wake word as something else, add that
  spelling to `LOREMASTER_WAKE_WORD_ALIASES`. "Warmaster" is already
  covered for the default wake word. If you set the list yourself,
  include `warmaster` in it to keep that.
- The wake word is "loremaster" even if your bot has another name in
  Discord. It works well because it's long and isn't an everyday word.
  If you change it, choose a distinctive word of three or more syllables.
  A short or common word ("Gary", "bot") wakes the bot by accident during
  normal conversation, and Whisper mishears short words more often.
- You can pause after the wake word. The bot waits about 8 seconds for
  the rest of the question.

Voice input depends on an unreleased py-cord commit. See
[bot/README.md](bot/README.md#voice-input-stt) for why, and for known
issues.

---

## Backups

`loremaster.db` changes during every session. To back it up as readable
SQL, run from `bot\`:

```
python export_db.py            # writes loremaster_backup.sql, WISHLIST.md and BUGS.md
python export_db.py --restore  # rebuilds loremaster.db from loremaster_backup.sql
```

The control panel's **Back up** button does the same export. If your home
folder is in a git repository, it also offers to commit and push the
backup files. It's safe to back up while the bot is running. `--restore`
won't overwrite an existing database.

If you keep backups in git, use a **private** repository. They contain
your group's campaign notes and members' names.

---

## Running it all the time

The bot only answers while it's running. The simplest option is to run it
on your own PC during game nights. For an always-on bot, any small machine
that stays on will do, such as a spare PC, a mini PC, or a small cloud
server. Spoken replies need a few GB of memory, and the first reply after
start-up takes longer while the model loads.

The bot holds one voice connection per server, and is designed for one
active channel per server.

---

## Costs

You pay Anthropic for every reply, according to your model's
[price per token](https://www.anthropic.com/pricing). What drives the
cost:

- **Instruction size.** The persona, the active game extension and
  campaign memory are sent with every reply. A large `project_files/`
  folder makes every reply more expensive.
- **Conversation length.** Up to the last 40 messages in the channel are
  sent too.
- **Tools.** Each tool call is another round trip to Claude. Web search
  is also billed per search, with at most 3 searches per request.
- **Images**, which count as tokens.

Watch **Usage** in the Anthropic Console for the first few sessions to see
what your group actually spends, and set a monthly limit under
**Billing**. Steam lookups and speech are free: speech runs on your
machine.

---

## Privacy: what's stored and what you should tell your group

As the operator, you're responsible for your bot. Nobody else sees your
data, but you should tell your group what it does.

**Sent to Anthropic** with every reply: the instructions (persona,
extension, campaign memory), recent channel messages that mention the bot,
the sender's display name, and attached images and files. See
[Anthropic's privacy policy](https://www.anthropic.com/legal/privacy) for
how it's handled.

**Stored on your machine:**

- `loremaster.db` keeps campaign notes, general memory, and wish-list and
  bug items. Feedback items record the author's Discord display name and
  user ID. They're sent to the developer only if you submit one as a
  GitHub issue yourself.
- `loremaster.log` keeps bot status messages and errors. It doesn't record
  messages or transcripts.
- Conversation history is kept in memory only and is lost on restart.

**Voice:**

- Spoken replies don't record anyone.
- While voice input is listening, everyone's speech in that voice channel
  is buffered in memory and sent to your Whisper server for
  transcription. Audio is never saved to disk. Only questions that follow
  the wake word go to Anthropic.
- Tell your members before you turn listening on, and make sure the bot's
  use of voice follows Discord's
  [Developer Policy](https://discord.com/developers/docs/policies-and-agreements/developer-policy).

---

## Upgrading

1. Stop the bot (with the control panel, or Ctrl+C).
2. Close the control panel too. On Windows, a running Python process can
   lock files and cause "Access is denied" during the install.
3. Update the code and the packages:

   ```
   git pull
   cd bot
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

4. Read [CHANGELOG.md](CHANGELOG.md) for anything you need to change, then
   start the bot again.

Your home folder (`.env`, `instructions/`, the database) isn't touched by
an upgrade.

### Older installs

Before 0.6.0, the database, backup, log and PID file were kept in `bot/`.
If `bot/loremaster.db` exists, the bot keeps using that layout. To move to
the new one, stop the bot and move those files up one folder, into the
home folder.

---

## Troubleshooting

**The bot is online but doesn't answer.** Check that **Message Content
Intent** is turned on (Developer Portal > Bot), that you @mentioned it
rather than just typing its name, and that it can see and post in that
channel.

**`KeyError: 'DISCORD_BOT_TOKEN'` at start-up.** The bot didn't find your
`.env`. It reads `.env` from the home folder: the clone folder, or
`LOREMASTER_HOME` if you set that.

**"voice on" fails.** The bot says which permission is missing. Usually a
single voice channel denies it View Channel, Connect or Speak.

**No sound from spoken replies.** Check that `ffmpeg -version` works in a
new terminal. Check the log for errors.

**Voice input hears nothing.** Check that the Whisper server is running
(`docker ps`) and reachable at `WHISPER_HOST:WHISPER_PORT`. A py-cord
warning like `Socket reader ... is waiting to be set as running` in the
middle of a session means voice receive stopped. Say "listen off", then
"listen on". [bot/README.md](bot/README.md#voice-input-stt) has more.

**The first reply after start-up is slow.** The speech model is loading.
Later replies are faster.

### Behind a corporate firewall or proxy

- If HTTPS is intercepted, point Python at your company's CA certificate
  with `SSL_CERT_FILE` and `REQUESTS_CA_BUNDLE`.
- If the Hugging Face model download fails, try `HF_HUB_DISABLE_XET=1`.
- If GitHub is blocked, `pip install -r requirements.txt` can't fetch
  py-cord, and the spaCy model can't download.

[voxport's README](https://github.com/brienalkire/voxport) covers the
speech-model parts in detail, including offline installs.

### Managed or locked-down computers

- Use `python -m pip ...` and `python main.py` rather than any `.exe`
  launchers, which some managed machines block.
- If PowerShell won't run `make_shortcut.ps1`, use
  `-ExecutionPolicy Bypass` as shown in [Start it](#5-start-it), or start
  the bot with `python main.py`.
- Discord's bot connection and Anthropic's API both need outbound HTTPS.
  Voice also needs outbound UDP.
