"""Session scanning and metadata extraction from Claude Code transcripts."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from .models import SessionSummary


# ---------------------------------------------------------------------------
# Constants — copied from session_explorer.py
# ---------------------------------------------------------------------------

DOMAIN_PATTERNS: dict[str, str] = {
    "research": r"\b(?:hypothesis|experiment|paper|finding|result|metric|arxiv)\b",
    "coding": r"\b(?:function|class|import|error|bug|test|refactor|compile)\b",
    "writing": r"\b(?:document|draft|section|paragraph|edit|review|write up)\b",
    "ops": r"\b(?:deploy|server|ssh|gpu|instance|pipeline|docker|remote)\b",
    "data": r"\b(?:dataset|dataframe|csv|json|table|query|sql|extract)\b",
    "analysis": r"\b(?:plot|chart|graph|compare|trend|correlation|cluster)\b",
    "communication": r"\b(?:slack|email|message|post|channel|team)\b",
}

TOPIC_PATTERNS: list[tuple[str, str]] = [
    (r"\b(?:trust|verification|provenance|ledger)\b", "trust-verification"),
    (r"\b(?:continual.?learning|forgetting|catastrophic)\b", "continual-learning"),
    (r"\b(?:experiment|baseline|benchmark)\b", "experimentation"),
    (r"\b(?:cedar|policy|formal.?verif)\b", "formal-verification"),
    (r"\b(?:hook|provenance|tracking|log)\b", "observability"),
    (r"\b(?:taxonomy|classify|cluster)\b", "taxonomy"),
    (r"\b(?:agent|autonomous|self.?improv)\b", "agents"),
    (r"\b(?:slack|email|team|meeting)\b", "communication"),
    (r"\b(?:gpu|training|fine.?tun)\b", "training-infra"),
    (r"\b(?:git|commit|branch|merge|pr)\b", "version-control"),
    (r"\b(?:notebook|explore|visuali)\b", "exploration"),
]

CORRECTION_RE = re.compile(
    r"\b(?:no[,.]?\s|actually|instead|don't|wrong|not\s+(?:that|what|right)|rephrase|still\s+mentions)\b",
    re.I,
)
APPROVAL_RE = re.compile(
    r"\b(?:yes|go ahead|commit|looks good|do it|post it|perfect|very good)\b",
    re.I,
)


# ---------------------------------------------------------------------------
# Extraction helpers — copied from session_explorer.py
# ---------------------------------------------------------------------------

def decode_project_key(key: str) -> tuple[str, str]:
    """Convert a project dir name to (path, short_name)."""
    path = key.replace("-", "/")
    if not path.startswith("/"):
        path = "/" + path
    parts = path.rstrip("/").split("/")
    short = "/".join(parts[-2:]) if len(parts) >= 2 else parts[-1]
    return path, short


def extract_human_prompts(entries: list[dict]) -> list[str]:
    """Extract human-authored messages (skip tool results and system messages)."""
    prompts: list[str] = []
    for e in entries:
        msg = e.get("message", {})
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        text = ""
        if isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    t = c.get("text", "").strip()
                    if t and not t.startswith("<"):
                        text = t
                        break
        elif isinstance(content, str):
            text = content.strip()
        if text and not text.startswith("<") and len(text) > 3:
            prompts.append(text[:300])
    return prompts


def extract_tools(entries: list[dict]) -> Counter:
    """Count tool usage across assistant messages."""
    tools: Counter = Counter()
    for e in entries:
        msg = e.get("message", {})
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", [])
        if isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    tools[c.get("name", "?")] += 1
    return tools


def extract_file_types(entries: list[dict]) -> list[str]:
    """Extract file extensions from tool call inputs."""
    extensions: set[str] = set()
    for e in entries:
        msg = e.get("message", {})
        content = msg.get("content", [])
        if isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    inp = c.get("input", {})
                    for v in inp.values():
                        if isinstance(v, str):
                            for m in re.finditer(r"[\w/.-]+\.(\w{1,8})\b", v):
                                extensions.add(m.group(1))
    return sorted(extensions)


def extract_domains(text: str) -> list[str]:
    """Identify domain signals from combined text."""
    lower = text.lower()
    return [d for d, pat in DOMAIN_PATTERNS.items() if re.search(pat, lower)]


def extract_topics(text: str) -> list[str]:
    """Extract topic tags from combined text."""
    lower = text.lower()
    topics = [topic for pat, topic in TOPIC_PATTERNS if re.search(pat, lower)]
    return sorted(set(topics))


# ---------------------------------------------------------------------------
# Session parser — extended from session_explorer.py
# ---------------------------------------------------------------------------

def parse_session(path: Path, project_key: str) -> SessionSummary | None:
    """Parse a single Claude Code session transcript into a SessionSummary."""
    entries: list[dict] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if len(entries) < 2:
        return None

    # Timestamps
    timestamps = [e.get("timestamp", "") for e in entries if e.get("timestamp")]
    if not timestamps:
        return None

    started = timestamps[0]
    ended = timestamps[-1]
    try:
        t0 = datetime.fromisoformat(started.rstrip("Z"))
        t1 = datetime.fromisoformat(ended.rstrip("Z"))
        duration = (t1 - t0).total_seconds() / 60.0
    except (ValueError, TypeError):
        duration = 0.0

    # Model
    model = ""
    for e in entries:
        m = e.get("message", {}).get("model", "")
        if m:
            model = m
            break

    # Git branch
    git_branch = ""
    for e in entries:
        gb = e.get("gitBranch", "")
        if gb:
            git_branch = gb
            break

    # Extended fields: slug, cwd, version, permission_mode
    slug = ""
    cwd = ""
    version = ""
    permission_mode = ""
    for e in entries:
        if not slug:
            slug = e.get("slug", "")
        if not cwd:
            cwd = e.get("cwd", "")
        if not version:
            version = e.get("version", "")
        if not permission_mode:
            permission_mode = e.get("permissionMode", "")
        if slug and cwd and version and permission_mode:
            break

    # Human prompts
    prompts = extract_human_prompts(entries)

    # Tools
    tools = extract_tools(entries)

    # File types
    file_types = extract_file_types(entries)

    # Combined text for domain/topic extraction
    combined_text = " ".join(prompts)

    # Trust signals
    corrections = sum(1 for p in prompts if CORRECTION_RE.search(p))
    approvals = sum(1 for p in prompts if APPROVAL_RE.search(p))

    # Token usage
    total_input = 0
    total_output = 0
    for e in entries:
        usage = e.get("message", {}).get("usage", {})
        if usage:
            total_input += usage.get("input_tokens", 0)
            total_output += usage.get("output_tokens", 0)

    # Subagent count
    session_dir = path.parent / path.stem
    subagent_count = 0
    if session_dir.is_dir():
        subagents_dir = session_dir / "subagents"
        if subagents_dir.is_dir():
            subagent_count = sum(1 for _ in subagents_dir.glob("agent-*.jsonl"))

    project_path, project_short = decode_project_key(project_key)

    stat = path.stat()

    return SessionSummary(
        session_id=path.stem,
        project_key=project_key,
        project_path=project_path,
        project_short=project_short,
        started_at=started,
        ended_at=ended,
        duration_minutes=round(duration, 1),
        total_entries=len(entries),
        human_prompt_count=len(prompts),
        tool_call_count=sum(tools.values()),
        model=model,
        first_prompt=prompts[0] if prompts else "",
        human_prompts=prompts,
        topics=extract_topics(combined_text),
        top_tools=tools.most_common(8),
        tools_used=sorted(tools.keys()),
        domains=extract_domains(combined_text),
        file_types=file_types,
        git_branch=git_branch,
        correction_count=corrections,
        approval_count=approvals,
        slug=slug,
        cwd=cwd,
        version=version,
        permission_mode=permission_mode,
        subagent_count=subagent_count,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        file_size=stat.st_size,
        file_mtime=stat.st_mtime,
    )


def scan_all_sessions(projects_dir: Path) -> list[SessionSummary]:
    """Scan all Claude Code projects and extract session summaries."""
    sessions: list[SessionSummary] = []
    for project_dir in sorted(projects_dir.iterdir()):
        if not project_dir.is_dir():
            continue
        project_key = project_dir.name
        for transcript in sorted(project_dir.glob("*.jsonl")):
            summary = parse_session(transcript, project_key)
            if summary:
                sessions.append(summary)
    sessions.sort(key=lambda s: s.started_at, reverse=True)
    return sessions
