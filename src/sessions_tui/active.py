"""Active session detection via IDE lock files and process inspection."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ActiveSession:
    """Info about a currently running Claude Code session."""

    pid: int
    ide_name: str = ""          # e.g. "Visual Studio Code"
    workspace_folders: list[str] | None = None
    status: str = "active"      # "active" | "thinking"


def detect_active_sessions(
    claude_dir: Path | None = None,
) -> dict[str, ActiveSession]:
    """Detect currently running Claude Code sessions.

    Returns a mapping of working-directory -> ActiveSession.
    We use working dirs as the join key since session IDs are not
    directly exposed in process args or lock files.
    """
    claude_dir = claude_dir or Path.home() / ".claude"
    active: dict[str, ActiveSession] = {}

    # Method 1: IDE lock files
    ide_dir = claude_dir / "ide"
    if ide_dir.is_dir():
        for lock_file in ide_dir.glob("*.lock"):
            try:
                data = json.loads(lock_file.read_text())
                pid = data.get("pid", 0)
                if pid and _is_pid_alive(pid):
                    folders = data.get("workspaceFolders", [])
                    ide = data.get("ideName", "")
                    for folder in folders:
                        active[folder] = ActiveSession(
                            pid=pid,
                            ide_name=ide,
                            workspace_folders=folders,
                        )
            except (json.JSONDecodeError, OSError):
                continue

    # Method 2: CLI processes
    try:
        result = subprocess.run(
            ["pgrep", "-af", "claude"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.strip().splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) < 2:
                continue
            try:
                pid = int(parts[0])
            except ValueError:
                continue
            cmd = parts[1]
            # Skip non-Claude processes and this grep itself
            if "claude" not in cmd.lower():
                continue
            # Already captured via lock file?
            if any(a.pid == pid for a in active.values()):
                continue
            active[f"cli:{pid}"] = ActiveSession(pid=pid, ide_name="CLI")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return active


def match_active_to_sessions(
    active: dict[str, ActiveSession],
    sessions_by_cwd: dict[str, list[str]],
) -> set[str]:
    """Match active working directories to session IDs.

    Args:
        active: Output from detect_active_sessions().
        sessions_by_cwd: Mapping of cwd -> list of session_ids that used that cwd.

    Returns:
        Set of session_ids that appear to be currently active.
    """
    active_ids: set[str] = set()
    for folder in active:
        if folder.startswith("cli:"):
            continue
        # Try exact and prefix matching
        for cwd, session_ids in sessions_by_cwd.items():
            if cwd == folder or cwd.startswith(folder) or folder.startswith(cwd):
                # The most recent session in this cwd is likely the active one
                if session_ids:
                    active_ids.add(session_ids[0])
    return active_ids


def _is_pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is alive."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
