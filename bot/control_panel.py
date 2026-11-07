"""Desktop start/stop control for the bot - no terminal needed.

Launch with the venv's pythonw.exe (no console window), e.g. from the
desktop shortcut (see make_shortcut.ps1). "Back up" runs export_db.py and
offers to commit + push the result. The bot runs as its own
background process with output going to loremaster.log, so closing this
window leaves it running; reopening the window finds it again via
.loremaster.pid.
"""

import ctypes
import os
import re
import subprocess
import sys
import tkinter as tk
from collections import deque
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

import paths

BOT_DIR = paths.CODE_DIR
# python.exe from the same environment as the pythonw.exe running this panel.
PYTHON = Path(sys.executable).with_name("python.exe")
MAIN = BOT_DIR / "main.py"
LOG_PATH = paths.LOG_PATH
PREV_LOG_PATH = paths.PREV_LOG_PATH
PID_PATH = paths.PID_PATH

AUTHOR = "Brien Alkire"

POLL_MS = 2000
LOG_LINES_SHOWN = 14
# Diagnostic / library chatter that would drown out what's worth seeing.
LOG_NOISE = ("DEBUG", "DeprecationWarning", "  def ", "  async def ")

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259


def _process_image(pid: int) -> str | None:
    """Full exe path of a live process, or None if it isn't running."""
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)) or exit_code.value != _STILL_ACTIVE:
            return None
        size = ctypes.c_ulong(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return None
        return buf.value
    finally:
        kernel32.CloseHandle(handle)


def running_pid() -> int | None:
    """PID of the bot this panel started, if it's still running. Checks the
    exe path too, so a recycled PID belonging to something else doesn't
    count."""
    try:
        pid = int(PID_PATH.read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return None
    image = _process_image(pid)
    if image and Path(image).resolve() == PYTHON.resolve():
        return pid
    return None


def other_bot_pids() -> list[int]:
    """Any main.py bot processes running from this folder, however they
    were started (a terminal, a Claude Code session) - two copies would
    answer every message twice."""
    query = (
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
        "Where-Object { $_.CommandLine -like '*main.py*' } | "
        "ForEach-Object { \"$($_.ProcessId)|$($_.CommandLine)\" }"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", query],
            capture_output=True, text=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    pids = []
    for line in out.splitlines():
        pid, _, cmdline = line.partition("|")
        if pid.strip().isdigit() and "loremaster" in cmdline.lower().replace("\\", "/"):
            pids.append(int(pid))
    return pids


def bot_version() -> str:
    """The bot's __version__, read from main.py's source - importing main
    would load the models and start the bot."""
    try:
        match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']',
                          MAIN.read_text(encoding="utf-8"), re.MULTILINE)
    except OSError:
        match = None
    return match.group(1) if match else "unknown"


def start_bot() -> int:
    if LOG_PATH.exists():
        LOG_PATH.replace(PREV_LOG_PATH)
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    with open(LOG_PATH, "w", encoding="utf-8") as log:
        log.write(f"--- started from control panel {datetime.now():%Y-%m-%d %H:%M:%S} ---\n")
        log.flush()
        proc = subprocess.Popen(
            [str(PYTHON), str(MAIN)], cwd=BOT_DIR, env=env,
            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    PID_PATH.write_text(f"{proc.pid} {datetime.now().isoformat(timespec='seconds')}")
    return proc.pid


def stop_bot(pid: int) -> None:
    # /T also ends the bot's ffmpeg children (spoken-reply playback).
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                   creationflags=subprocess.CREATE_NO_WINDOW)
    PID_PATH.unlink(missing_ok=True)


def recent_log_lines() -> list[str]:
    try:
        with open(LOG_PATH, encoding="utf-8", errors="replace") as f:
            lines = deque((l.rstrip() for l in f if l.strip() and not any(n in l for n in LOG_NOISE)),
                          maxlen=LOG_LINES_SHOWN)
    except OSError:
        return []
    return [l if len(l) <= 160 else l[:157] + "..." for l in lines]


def _git(*args: str, timeout: int = 60, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd or REPO_DIR, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout,
                          creationflags=subprocess.CREATE_NO_WINDOW)


def _item_ids(markdown: str) -> set[int]:
    return {int(n) for n in re.findall(r"^- \*\*#(\d+)\*\*", markdown, re.MULTILINE)}


def _backup_repo() -> Path | None:
    """The git work tree holding the backup files, or None if they aren't in
    one. Only then does "Back up" offer to commit and push."""
    try:
        top = _git("rev-parse", "--show-toplevel", cwd=paths.BACKUP_PATH.parent)
    except (OSError, subprocess.SubprocessError):
        return None
    return Path(top.stdout.strip()).resolve() if top.returncode == 0 and top.stdout.strip() else None


REPO_DIR = _backup_repo()


def backup_changes(files: list[Path]) -> tuple[list[str], list[str]]:
    """(changed repo-relative paths, human-readable summary lines) for the
    exported files vs. the last commit."""
    rel = [p.resolve().relative_to(REPO_DIR).as_posix() for p in files if REPO_DIR in p.resolve().parents]
    status = _git("status", "--porcelain", "--", *rel).stdout
    changed = [line[3:].strip() for line in status.splitlines() if line.strip()]
    summary = []
    for path, label in ((paths.WISHLIST_PATH, "wish"), (paths.BUGS_PATH, "bug report")):
        if REPO_DIR not in path.resolve().parents:
            continue
        before = _git("show", f"HEAD:{path.resolve().relative_to(REPO_DIR).as_posix()}").stdout
        new = len(_item_ids(path.read_text(encoding="utf-8")) - _item_ids(before))
        if new:
            summary.append(f"{new} new {label}{'s' if new != 1 else ''}")
    if any(c.endswith("loremaster_backup.sql") for c in changed) and not summary:
        summary.append("campaign memory or item statuses updated")
    elif any(c.endswith("loremaster_backup.sql") for c in changed):
        summary.append("plus any campaign memory / status updates")
    return changed, summary


class ControlPanel(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Loremaster")
        self.geometry("720x380")
        self.minsize(480, 260)

        menubar = tk.Menu(self, tearoff=False)
        menubar.add_command(label="About", command=self.show_about)
        self.config(menu=menubar)

        top = tk.Frame(self, padx=12, pady=10)
        top.pack(fill="x")
        self.status = tk.Label(top, font=("Segoe UI", 13, "bold"), anchor="w")
        self.status.pack(side="left", fill="x", expand=True)
        tk.Button(top, text="Open log", width=10, command=self.open_log).pack(side="right", padx=(6, 0))
        tk.Button(top, text="Back up", width=10, command=self.back_up).pack(side="right", padx=(6, 0))
        self.stop_button = tk.Button(top, text="Stop", width=10, command=self.stop)
        self.stop_button.pack(side="right", padx=(6, 0))
        self.start_button = tk.Button(top, text="Start", width=10, command=self.start)
        self.start_button.pack(side="right")

        self.log_view = tk.Text(self, height=LOG_LINES_SHOWN, font=("Consolas", 9), wrap="none",
                                state="disabled", padx=8, pady=6, relief="flat", background="#f4f4f4")
        self.log_view.pack(fill="both", expand=True, padx=12)
        tk.Label(self, text="Closing this window leaves the bot running.", fg="#666",
                 anchor="w", padx=12, pady=6).pack(fill="x")

        self._poll()

    def _poll(self):
        self.refresh()
        self.after(POLL_MS, self._poll)

    def refresh(self):
        pid = running_pid()
        if pid:
            since = PID_PATH.read_text().split()[1] if PID_PATH.exists() else "?"
            self.status.config(text=f"● Running  (since {since.replace('T', ' ')})", fg="#1a7f37")
        else:
            self.status.config(text="● Stopped", fg="#b42318")
        self.start_button.config(state="disabled" if pid else "normal")
        self.stop_button.config(state="normal" if pid else "disabled")

        self.log_view.config(state="normal")
        self.log_view.delete("1.0", "end")
        self.log_view.insert("end", "\n".join(recent_log_lines()))
        self.log_view.see("end")
        self.log_view.config(state="disabled")

    def start(self):
        others = other_bot_pids()
        if others:
            if not messagebox.askyesno(
                "Loremaster is already running",
                f"Another copy of the bot is already running (PID {', '.join(map(str, others))}) - "
                "two copies would answer every message twice.\n\nStop it and start a fresh one?"):
                return
            for pid in others:
                stop_bot(pid)
        start_bot()
        self.refresh()

    def stop(self):
        pid = running_pid()
        if pid and messagebox.askyesno("Stop Loremaster", "Stop the bot? It will leave voice and stop answering."):
            stop_bot(pid)
            self.refresh()

    def back_up(self):
        import export_db  # here, not at top: only needed when backing up
        self.config(cursor="watch")
        self.update()
        try:
            try:
                export_db.export()
            except Exception as exc:  # noqa: BLE001 - show it, don't crash the panel
                messagebox.showerror("Back up failed", f"Export failed:\n{exc}")
                return
            exported = [export_db.BACKUP_PATH, *export_db.FEEDBACK_PATHS.values()]
            if REPO_DIR is None:
                messagebox.showinfo("Back up", f"Exported to {export_db.BACKUP_PATH.parent}.")
                return
            changed, summary = backup_changes(exported)
            if not changed:
                messagebox.showinfo("Back up", "Exported - no changes since the last backup commit.")
                return
            detail = "\n".join(f"  - {line}" for line in summary) or "  - backup files updated"
            if not messagebox.askyesno(
                    "Back up",
                    f"Exported. Changes since the last backup:\n{detail}\n\n"
                    "Commit and push these backup files now?\n"
                    "(Only these files - nothing else you're working on.)"):
                messagebox.showinfo("Back up", "Exported, not committed. Commit them whenever you like.")
                return
            message = f"Back up campaign memory and feedback ({datetime.now():%Y-%m-%d})"
            _git("add", "--", *changed)
            commit = _git("commit", "--only", "-m", message, "--", *changed)
            if commit.returncode != 0:
                messagebox.showerror("Back up", f"Commit failed:\n{(commit.stderr or commit.stdout).strip()}")
                return
            push = _git("push", timeout=120)
            if push.returncode != 0:
                messagebox.showwarning("Back up", "Committed locally, but the push failed - push later.\n\n"
                                       f"{push.stderr.strip()[-400:]}")
                return
            messagebox.showinfo("Back up", "Backed up, committed, and pushed.")
        finally:
            self.config(cursor="")

    def show_about(self):
        messagebox.showinfo("About Loremaster",
                            f"Loremaster\n\nVersion {bot_version()}\nAuthor: {AUTHOR}", parent=self)

    def open_log(self):
        if LOG_PATH.exists():
            os.startfile(LOG_PATH)
        else:
            messagebox.showinfo("Loremaster", "No log yet - start the bot first.")


if __name__ == "__main__":
    if sys.platform != "win32":
        sys.exit("control_panel.py is Windows-only.")
    ControlPanel().mainloop()
