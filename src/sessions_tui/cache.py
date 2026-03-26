"""Incremental JSON cache for session metadata.

Avoids re-parsing unchanged session files by tracking file size and mtime.
First run: ~1s (full parse). Subsequent runs with few changes: <200ms.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .models import SessionSummary
from .scanner import parse_session

CACHE_VERSION = 2


def _session_from_dict(d: dict) -> SessionSummary:
    """Reconstruct a SessionSummary from a cached dict."""
    # top_tools is stored as list of [name, count] pairs in JSON
    d["top_tools"] = [tuple(t) for t in d.get("top_tools", [])]
    return SessionSummary(**d)


def load_or_rebuild(
    projects_dir: Path,
    cache_path: Path,
    force_refresh: bool = False,
) -> list[SessionSummary]:
    """Load cached sessions, incrementally updating only changed/new files."""
    cached: dict[str, dict] = {}

    # Load existing cache
    if not force_refresh and cache_path.exists():
        try:
            with open(cache_path) as f:
                data = json.load(f)
            if data.get("version") == CACHE_VERSION:
                for entry in data.get("sessions", []):
                    cached[entry["session_id"]] = entry
        except (json.JSONDecodeError, KeyError):
            cached = {}

    # Walk all session JSONL files
    current_files: dict[str, tuple[Path, str]] = {}  # session_id -> (path, project_key)
    for project_dir in sorted(projects_dir.iterdir()):
        if not project_dir.is_dir():
            continue
        project_key = project_dir.name
        for transcript in project_dir.glob("*.jsonl"):
            session_id = transcript.stem
            current_files[session_id] = (transcript, project_key)

    sessions: list[SessionSummary] = []
    changed = 0

    for session_id, (path, project_key) in current_files.items():
        try:
            stat = path.stat()
        except OSError:
            continue

        # Check if cached entry is still valid
        if session_id in cached:
            entry = cached[session_id]
            if entry.get("file_size") == stat.st_size and entry.get("file_mtime") == stat.st_mtime:
                sessions.append(_session_from_dict(entry))
                continue

        # Re-parse changed or new session
        summary = parse_session(path, project_key)
        if summary:
            sessions.append(summary)
            changed += 1

    # Remove stale entries (files that no longer exist) is implicit —
    # we only add sessions found on disk.

    sessions.sort(key=lambda s: s.ended_at, reverse=True)

    # Save updated cache
    if changed > 0 or not cache_path.exists():
        _save_cache(sessions, cache_path)

    return sessions


def _save_cache(sessions: list[SessionSummary], cache_path: Path) -> None:
    """Write the session cache to disk."""
    os.makedirs(cache_path.parent, exist_ok=True)
    data = {
        "version": CACHE_VERSION,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "session_count": len(sessions),
        "sessions": [asdict(s) for s in sessions],
    }
    tmp = cache_path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, separators=(",", ":"), default=str)
    tmp.replace(cache_path)
