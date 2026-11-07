"""Back up the campaign-memory database as a committable SQL text dump.

loremaster.db is live state the bot rewrites during sessions, so it's
gitignored - a binary file git can't diff or merge. This writes
loremaster_backup.sql instead: readable, diffable (you can see what the
bot remembered each session), and enough to rebuild the database. It
also writes WISHLIST.md and BUGS.md, the group's feedback in readable
form. All of these live under LOREMASTER_HOME (see paths.py).

    python export_db.py            # loremaster.db -> loremaster_backup.sql + WISHLIST.md, BUGS.md
    python export_db.py --restore  # loremaster_backup.sql -> loremaster.db

Safe to run while the bot is up: the export snapshots the database via
SQLite's backup API, so it never captures a half-finished write.
"""

import argparse
import sqlite3
import sys

import feedback
import paths

DB_PATH = paths.DB_PATH
BACKUP_PATH = paths.BACKUP_PATH
FEEDBACK_PATHS = {"wish": paths.WISHLIST_PATH, "bug": paths.BUGS_PATH}


def export() -> None:
    source = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    snapshot = sqlite3.connect(":memory:")
    source.backup(snapshot)
    source.close()
    with open(BACKUP_PATH, "w", encoding="utf-8", newline="\n") as f:
        for line in snapshot.iterdump():
            f.write(line + "\n")
    for kind, path in FEEDBACK_PATHS.items():
        path.write_text(feedback.to_markdown(snapshot, kind), encoding="utf-8", newline="\n")
    snapshot.close()
    names = ", ".join(p.name for p in FEEDBACK_PATHS.values())
    print(f"Exported {DB_PATH.name} -> {BACKUP_PATH.name}, {names}")


def restore() -> None:
    if DB_PATH.exists():
        sys.exit(f"{DB_PATH.name} already exists - move it aside first; "
                 "refusing to overwrite live campaign memory.")
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(BACKUP_PATH.read_text(encoding="utf-8"))
    conn.close()
    print(f"Restored {BACKUP_PATH.name} -> {DB_PATH.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--restore", action="store_true",
                        help="rebuild loremaster.db from loremaster_backup.sql")
    restore() if parser.parse_args().restore else export()
