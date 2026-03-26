"""Session list using Textual's OptionList with collapsible groups and fork graph."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from ..models import SessionSummary

# Prefix for group header option IDs
_HDR = "hdr-"
# Prefix for session card option IDs
_SES = "s-"

# Git-style graph characters — bright colors for visibility
_GRAPH_STYLE = "bold #79c0ff"    # bright blue for graph lines
_FORK_STYLE = "bold #ffa657"     # bright orange for fork connectors
_FORK_BADGE_STYLE = "bold #ffa657"  # orange badge for forked sessions


class SessionSelected(Message):
    """Emitted when a session is selected in the list."""

    def __init__(self, session_id: str) -> None:
        super().__init__()
        self.session_id = session_id


# ---------------------------------------------------------------------------
# Fork tree builder
# ---------------------------------------------------------------------------

def _build_fork_trees(sessions: list[SessionSummary]) -> list[SessionSummary]:
    """Reorder sessions so forked children appear directly after their parent,
    and return them with graph metadata attached.

    Each session gets two transient attributes set:
      _graph_prefix: str  — the git-style graph characters to prepend
      _fork_depth: int    — depth in the fork tree (0 = root)
    """
    by_id: dict[str, SessionSummary] = {s.session_id: s for s in sessions}
    children: dict[str, list[str]] = {}  # parent_id -> [child_ids]
    roots: list[str] = []

    for s in sessions:
        if s.forked_from and s.forked_from in by_id:
            children.setdefault(s.forked_from, []).append(s.session_id)
        else:
            roots.append(s.session_id)

    # If no forks at all, return as-is with no graph prefix
    if not children:
        for s in sessions:
            s._graph_prefix = ""  # type: ignore[attr-defined]
            s._fork_depth = 0     # type: ignore[attr-defined]
        return sessions

    # DFS to produce ordered list with graph lines
    result: list[SessionSummary] = []

    def walk(sid: str, depth: int, is_last: bool, prefix_parts: list[str]) -> None:
        s = by_id[sid]
        kids = children.get(sid, [])
        # Sort children by ended_at descending (most recent first)
        kids.sort(key=lambda c: by_id[c].ended_at, reverse=True)

        # Build the graph prefix for this node
        if depth == 0:
            if kids:
                graph = "● "  # root with children
            else:
                graph = ""    # standalone root, no graph
        else:
            connector = "└─" if is_last else "├─"
            graph = "".join(prefix_parts) + connector + " "

        s._graph_prefix = graph   # type: ignore[attr-defined]
        s._fork_depth = depth     # type: ignore[attr-defined]
        result.append(s)

        # Prefix for children of this node
        if depth == 0:
            child_prefix = []
        else:
            child_prefix = prefix_parts + ["  " if is_last else "│ "]

        for i, kid_id in enumerate(kids):
            is_last_kid = (i == len(kids) - 1)
            walk(kid_id, depth + 1, is_last_kid, child_prefix)

    for rid in roots:
        walk(rid, 0, True, [])

    return result


# ---------------------------------------------------------------------------
# Widget
# ---------------------------------------------------------------------------

class SessionList(Vertical):
    """Scrollable grouped session list with collapsible sections and fork graph."""

    DIMENSIONS = ("project", "topic", "domain", "date", "branch")

    dimension: reactive[str] = reactive("project")

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._sessions: list[SessionSummary] = []
        self._display_sessions: list[SessionSummary] = []  # filtered subset
        self._id_map: dict[str, str] = {}       # option_id -> session_id
        self._group_map: dict[str, str] = {}     # option_id -> group_label
        self._collapsed: set[str] = set()        # collapsed group labels
        self._group_labels: list[str] = []       # ordered group labels
        self._grouped_data: list[tuple[str, list[SessionSummary]]] = []

    def compose(self) -> ComposeResult:
        yield OptionList(id="session-options")

    def set_sessions(self, sessions: list[SessionSummary]) -> None:
        """Replace all session data and rebuild the list."""
        self._sessions = sessions
        self._display_sessions = sessions
        self._collapsed.clear()
        self._rebuild()

    def set_filtered(self, sessions: list[SessionSummary]) -> None:
        """Set the display list to a filtered/ranked subset (from search)."""
        self._display_sessions = sessions
        self._collapsed.clear()
        self._rebuild()

    def _group_sessions(self, sessions: list[SessionSummary]) -> list[tuple[str, list[SessionSummary]]]:
        """Group sessions by the current dimension."""
        groups: dict[str, list[SessionSummary]] = {}
        for s in sessions:
            match self.dimension:
                case "project":
                    keys = [s.project_short]
                case "topic":
                    keys = s.topics if s.topics else ["untagged"]
                case "domain":
                    keys = s.domains if s.domains else ["untagged"]
                case "date":
                    keys = [s.started_at[:10]] if s.started_at else ["unknown"]
                case "branch":
                    keys = [s.git_branch or "unknown"]
                case _:
                    keys = [s.project_short]
            for key in keys:
                groups.setdefault(key, []).append(s)
        return sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))

    def _rebuild(self) -> None:
        """Rebuild the option list, respecting collapsed state and fork trees."""
        option_list = self.query_one("#session-options", OptionList)
        option_list.clear_options()
        self._id_map.clear()
        self._group_map.clear()

        self._grouped_data = self._group_sessions(self._display_sessions)
        self._group_labels = [label for label, _ in self._grouped_data]

        counter = 0
        for label, items in self._grouped_data:
            is_collapsed = label in self._collapsed
            arrow = "▶" if is_collapsed else "▼"

            # Group header
            hdr_id = f"{_HDR}{counter}"
            self._group_map[hdr_id] = label
            header_text = Text(f"{arrow} {label} ({len(items)})", style="bold #f0f6fc")
            option_list.add_option(Option(header_text, id=hdr_id))

            if not is_collapsed:
                # Sort by most recently active, then apply fork tree ordering
                items_sorted = sorted(items, key=lambda s: (not s.is_active, s.ended_at), reverse=True)
                items_with_graph = _build_fork_trees(items_sorted)

                for s in items_with_graph:
                    counter += 1
                    opt_id = f"{_SES}{counter}"
                    self._id_map[opt_id] = s.session_id
                    self._group_map[opt_id] = label

                    graph_prefix = getattr(s, "_graph_prefix", "")
                    fork_depth = getattr(s, "_fork_depth", 0)

                    dot = "●" if s.is_active else "○"
                    dot_style = "green" if s.is_active else "#484f58"

                    # Max chars per line in the left pane (pane is 40 wide, minus padding)
                    MAX_W = 36

                    card = Text(no_wrap=True, overflow="ellipsis")

                    # Git-style graph prefix (when parent is in same group)
                    if graph_prefix:
                        card.append(graph_prefix, style=_FORK_STYLE if fork_depth > 0 else _GRAPH_STYLE)
                    # Always show fork badge if session is forked (even if parent is in another group)
                    elif s.forked_from:
                        card.append("↳ ", style=_FORK_BADGE_STYLE)

                    card.append(f"{dot} ", style=dot_style)

                    # Trim name to fit on one line
                    prefix_len = len(graph_prefix) if graph_prefix else (2 if s.forked_from else 0)
                    avail = MAX_W - prefix_len - 2  # 2 for dot+space
                    name = s.display_name[:avail]
                    card.append(f"{name}\n", style="#c9d1d9")

                    # Meta line — indented to align with name
                    indent = " " * (prefix_len + 2)
                    meta = f"{s.project_short} · {s.duration_display} · {s.last_active_display}"
                    card.append(f"{indent}{meta[:MAX_W]}", style="#8b949e")

                    tags = " ".join(s.domains[:2]) if s.domains else ""
                    if tags:
                        card.append(f"\n{indent}{tags[:MAX_W]}", style="#484f58")

                    option_list.add_option(Option(card, id=opt_id))

            counter += 1

    def toggle_group(self, collapse: bool) -> None:
        """Collapse or expand the group the cursor is currently on/in."""
        option_list = self.query_one("#session-options", OptionList)
        highlighted = option_list.highlighted
        if highlighted is None:
            return

        try:
            option = option_list.get_option_at_index(highlighted)
        except Exception:
            return

        opt_id = option.id or ""
        group_label = self._group_map.get(opt_id)
        if not group_label:
            return

        changed = False
        if collapse and group_label not in self._collapsed:
            self._collapsed.add(group_label)
            changed = True
        elif not collapse and group_label in self._collapsed:
            self._collapsed.discard(group_label)
            changed = True

        if changed:
            self._rebuild()
            self._focus_group_header(group_label, option_list)

    def _focus_group_header(self, label: str, option_list: OptionList) -> None:
        """Move the cursor to a specific group's header."""
        for opt_id, grp in self._group_map.items():
            if grp == label and opt_id.startswith(_HDR):
                for i in range(option_list.option_count):
                    try:
                        opt = option_list.get_option_at_index(i)
                        if opt.id == opt_id:
                            option_list.highlighted = i
                            return
                    except Exception:
                        continue
                break

    def watch_dimension(self, _old: str, _new: str) -> None:
        if self._sessions:
            self._collapsed.clear()
            self._rebuild()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Forward session selection to the app, or toggle group on header."""
        opt_id = event.option.id or ""
        if opt_id.startswith(_HDR):
            label = self._group_map.get(opt_id)
            if label:
                if label in self._collapsed:
                    self._collapsed.discard(label)
                else:
                    self._collapsed.add(label)
                self._rebuild()
                option_list = self.query_one("#session-options", OptionList)
                self._focus_group_header(label, option_list)
        elif opt_id in self._id_map:
            session_id = self._id_map[opt_id]
            self.post_message(SessionSelected(session_id))

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        """Update detail pane on cursor movement."""
        opt_id = event.option.id or ""
        if opt_id in self._id_map:
            session_id = self._id_map[opt_id]
            self.post_message(SessionSelected(session_id))

    def get_highlighted_session_id(self) -> str | None:
        """Return the session_id of the currently highlighted option, or None."""
        option_list = self.query_one("#session-options", OptionList)
        highlighted = option_list.highlighted
        if highlighted is None:
            return None
        try:
            option = option_list.get_option_at_index(highlighted)
        except Exception:
            return None
        opt_id = option.id or ""
        return self._id_map.get(opt_id)
