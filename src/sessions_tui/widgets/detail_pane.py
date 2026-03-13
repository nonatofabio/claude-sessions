"""Detail pane showing full session metadata, tags, and prompts."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from ..models import SessionSummary
from ..scanner import APPROVAL_RE, CORRECTION_RE


class DetailPane(VerticalScroll):
    """Right pane: detailed view of a selected session."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._session: SessionSummary | None = None

    def compose(self) -> ComposeResult:
        yield Static("Select a session from the sidebar", classes="empty-state", id="detail-content")

    def show_session(self, session: SessionSummary) -> None:
        """Render full detail for the given session."""
        self._session = session
        content = self.query_one("#detail-content", Static)
        content.remove_class("empty-state")
        content.update(self._render_detail(session))

    def _render_detail(self, s: SessionSummary) -> str:
        """Build Rich markup for the session detail view."""
        lines: list[str] = []

        # Title
        status = "[green]● Active[/]" if s.is_active else "[#484f58]○ Idle[/]"
        name = s.display_name[:80]
        lines.append(f"[bold #f0f6fc]{name}[/]  {status}")
        lines.append("")

        # Metadata grid
        model_short = s.model.replace("claude-", "").replace("-", " ") if s.model else "unknown"
        lines.append(f"[#8b949e]Project:[/]  {s.project_short}")
        lines.append(f"[#8b949e]Branch:[/]   {s.git_branch or 'unknown'}    [#8b949e]Model:[/] {model_short}")
        started = s.started_at[:16].replace("T", " ") if s.started_at else "?"
        lines.append(f"[#8b949e]Started:[/]  {started}  ({s.duration_display})")
        lines.append(f"[#8b949e]Mode:[/]     {s.permission_mode or 'default'}    [#8b949e]Version:[/] {s.version or '?'}")
        if s.cwd:
            cwd_display = s.cwd.replace(str(Path.home()), "~")
            lines.append(f"[#8b949e]CWD:[/]      {cwd_display}")
        if s.slug:
            lines.append(f"[#8b949e]Slug:[/]     {s.slug}")
        lines.append("")

        # Stats
        lines.append(
            f"[#8b949e]Prompts:[/] {s.human_prompt_count}  "
            f"[#8b949e]Tools:[/] {s.tool_call_count}  "
            f"[#8b949e]Entries:[/] {s.total_entries}  "
            f"[#8b949e]Subagents:[/] {s.subagent_count}"
        )

        # Trust signals
        other = s.human_prompt_count - s.approval_count - s.correction_count
        lines.append(
            f"[green]● {s.approval_count} approvals[/]  "
            f"[#f85149]● {s.correction_count} corrections[/]  "
            f"[#8b949e]● {max(0, other)} other[/]"
        )

        # Token usage
        if s.total_input_tokens or s.total_output_tokens:
            inp_k = s.total_input_tokens / 1000
            out_k = s.total_output_tokens / 1000
            lines.append(f"[#8b949e]Tokens:[/] {inp_k:.1f}k in / {out_k:.1f}k out")
        lines.append("")

        # Tags: topics
        if s.topics:
            topic_tags = " ".join(f"[green]{t}[/]" for t in s.topics)
            lines.append(f"[#8b949e]Topics:[/]  {topic_tags}")

        # Tags: domains
        if s.domains:
            domain_tags = " ".join(f"[#58a6ff]{d}[/]" for d in s.domains)
            lines.append(f"[#8b949e]Domains:[/] {domain_tags}")

        # Tags: top tools
        if s.top_tools:
            tool_tags = " ".join(f"[#d29922]{name}({cnt})[/]" for name, cnt in s.top_tools[:6])
            lines.append(f"[#8b949e]Tools:[/]   {tool_tags}")

        lines.append("")

        # Human prompts
        if s.human_prompts:
            lines.append("[#8b949e]─── Human Prompts ───[/]")
            for prompt in s.human_prompts:
                truncated = prompt[:200]
                if CORRECTION_RE.search(prompt):
                    lines.append(f"[#f85149]▎[/] {_escape(truncated)}")
                elif APPROVAL_RE.search(prompt):
                    lines.append(f"[green]▎[/] {_escape(truncated)}")
                else:
                    lines.append(f"[#30363d]▎[/] {_escape(truncated)}")

        return "\n".join(lines)


def _escape(text: str) -> str:
    """Escape Rich markup characters in user text."""
    return text.replace("[", "\\[").replace("]", "\\]")
