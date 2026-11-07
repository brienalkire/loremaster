# Example Game Extension

A game extension adds game-specific instructions on top of the persona. To
make one, copy this folder to `instructions/<game>/` in your
LOREMASTER_HOME folder, rename this file to `instructions_<game>_rag.md`,
and replace the contents. Then ask the bot to create a campaign for
`<game>` (or set `GAME_EXTENSION=<game>` in `.env`).

What gets loaded while a campaign for this game is active:

- this file
- every `.md` file in `project_files/`, in name order
- the tools listed in `plugins.txt`, if there is one (see
  `bot/plugins/__init__.py`)

All of it goes into every request, so keep it to what the bot really
needs. Only add `project_files/` text you wrote yourself or have the right
to use. Copying wiki pages or community guides here can break their
licences.

---

## The party

Who plays which character, and each character's role. For example:

- **PlayerOne**: front-line tank
- **PlayerTwo**: healer and support

## How we play

- Difficulty, house rules, and anything else the bot should assume
- What kind of advice the group wants: full builds, or just hints?
- Spoilers: say whether the bot should avoid story spoilers

## Conventions

Words the group uses for things in this game, abbreviations, or naming
rules for bases and characters.
