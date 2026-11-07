"""Where loremaster keeps its user data, and the settings read from .env.

Everything that belongs to one group (the bot token in .env, the campaign
memory database, logs, the persona and game extensions) lives under one
home folder, separate from the code:

    LOREMASTER_HOME env var, if set
    otherwise the source checkout (the folder above bot/)

Home layout:

    .env                    secrets and settings (see .env.example)
    instructions/           persona.md + one folder per game extension
    loremaster.db           campaign memory, wish list, bug reports
    loremaster_backup.sql   text backup made by export_db.py
    WISHLIST.md, BUGS.md    readable feedback exports
    loremaster.log          bot output when started from the control panel

Older checkouts kept the database, backup, log and PID file in bot/. If
home is the checkout and bot/loremaster.db exists, those four stay in
bot/ so an existing install keeps working. To move to the new layout, stop
the bot and move them up one folder.

If home has no instructions/ folder, the bundled examples/instructions/
are used, so a fresh clone runs before any persona is written.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

CODE_DIR = Path(__file__).resolve().parent  # bot/
CHECKOUT_DIR = CODE_DIR.parent
CHANGELOG_PATH = CHECKOUT_DIR / "CHANGELOG.md"
EXAMPLE_INSTRUCTIONS_DIR = CHECKOUT_DIR / "examples" / "instructions"

HOME = Path(os.environ.get("LOREMASTER_HOME") or CHECKOUT_DIR).expanduser().resolve()

# Loaded before anything reads a setting. Real environment variables win
# over .env values.
load_dotenv(HOME / ".env")

_legacy_layout = HOME == CHECKOUT_DIR and (CODE_DIR / "loremaster.db").exists()
DATA_DIR = CODE_DIR if _legacy_layout else HOME
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "loremaster.db"
BACKUP_PATH = DATA_DIR / "loremaster_backup.sql"
LOG_PATH = DATA_DIR / "loremaster.log"
PREV_LOG_PATH = DATA_DIR / "loremaster.prev.log"
PID_PATH = DATA_DIR / ".loremaster.pid"
WISHLIST_PATH = HOME / "WISHLIST.md"
BUGS_PATH = HOME / "BUGS.md"

_home_instructions = HOME / "instructions"
INSTRUCTIONS_DIR = _home_instructions if _home_instructions.is_dir() else EXAMPLE_INSTRUCTIONS_DIR

# The persona file. persona.md is the new name; the old name still works.
_PERSONA_NAMES = ("persona.md", "instructions_gameassistant_base.md")


def persona_path() -> Path:
    for name in _PERSONA_NAMES:
        path = INSTRUCTIONS_DIR / name
        if path.exists():
            return path
    raise FileNotFoundError(
        f"No persona file in {INSTRUCTIONS_DIR} - expected one of {', '.join(_PERSONA_NAMES)}. "
        f"Copy {EXAMPLE_INSTRUCTIONS_DIR / 'persona.md'} there to start."
    )


def env_str(name: str, default: str = "") -> str:
    return (os.environ.get(name) or "").strip() or default


def env_bool(name: str, default: bool = False) -> bool:
    value = env_str(name).lower()
    if not value:
        return default
    return value in ("1", "true", "yes", "on")


def env_list(name: str) -> tuple[str, ...]:
    """Comma-separated values, blanks dropped, lowercased."""
    return tuple(v.strip().lower() for v in env_str(name).split(",") if v.strip())


def env_int(name: str, default: int) -> int:
    value = env_str(name)
    return int(value) if value else default
