"""Data models for session metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class SessionSummary:
    """Compact metadata for one Claude Code conversation session."""

    session_id: str
    project_key: str                     # raw dir name from .claude/projects/
    project_path: str                    # decoded path
    project_short: str                   # human-friendly short name

    started_at: str                      # ISO timestamp
    ended_at: str                        # ISO timestamp
    duration_minutes: float

    total_entries: int
    human_prompt_count: int
    tool_call_count: int
    model: str

    first_prompt: str                    # first human message (truncated)
    human_prompts: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)

    top_tools: list[tuple[str, int]] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)

    domains: list[str] = field(default_factory=list)
    file_types: list[str] = field(default_factory=list)

    git_branch: str = ""

    correction_count: int = 0
    approval_count: int = 0

    # Extended fields (beyond original session_explorer)
    slug: str = ""                       # e.g. "keen-leaping-fountain"
    cwd: str = ""                        # working directory
    version: str = ""                    # Claude Code version
    permission_mode: str = ""            # "default" | "bypassPermissions"
    subagent_count: int = 0              # number of subagent JSONL files
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    is_active: bool = False              # set at runtime, not persisted

    # Cache invalidation fields
    file_size: int = 0
    file_mtime: float = 0.0

    @property
    def display_name(self) -> str:
        """Best available human-readable name for this session."""
        if self.first_prompt:
            return self.first_prompt[:80]
        if self.slug:
            return self.slug
        return self.session_id[:12]

    @property
    def duration_display(self) -> str:
        """Human-friendly duration string."""
        mins = self.duration_minutes
        if mins < 1:
            return "<1m"
        if mins < 60:
            return f"{int(mins)}m"
        hours = mins / 60
        if hours < 24:
            return f"{hours:.1f}h"
        days = hours / 24
        return f"{days:.1f}d"

    @property
    def last_active_display(self) -> str:
        """Relative time since last message, e.g. '5m ago', '2h ago', '3d ago'."""
        if not self.ended_at:
            return "?"
        try:
            ended = datetime.fromisoformat(self.ended_at.rstrip("Z")).replace(tzinfo=timezone.utc)
            delta = datetime.now(timezone.utc) - ended
            secs = delta.total_seconds()
            if secs < 60:
                return "just now"
            if secs < 3600:
                return f"{int(secs // 60)}m ago"
            if secs < 86400:
                return f"{int(secs // 3600)}h ago"
            days = secs / 86400
            if days < 30:
                return f"{int(days)}d ago"
            return f"{int(days // 30)}mo ago"
        except (ValueError, TypeError):
            return "?"
