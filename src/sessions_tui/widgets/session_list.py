"""Session list using Textual's OptionList with collapsible groups."""

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


class SessionSelected(Message):
    """Emitted when a session is selected in the list."""

    def __init__(self, session_id: str) -> None:
        super().__init__()
        self.session_id = session_id


class SessionList(Vertical):
    """Scrollable grouped session list with collapsible sections."""

    DIMENSIONS = ("project", "topic", "domain", "date", "branch")

    dimension: reactive[str] = reactive("project")
    filter_text: reactive[str] = reactive("")

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._sessions: list[SessionSummary] = []
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
        self._collapsed.clear()
        self._rebuild()

    def _filtered(self) -> list[SessionSummary]:
        """Apply text filter to sessions."""
        if not self.filter_text:
            return self._sessions
        q = self.filter_text.lower()
        results = []
        for s in self._sessions:
            haystack = " ".join([
                s.project_short, s.first_prompt, s.git_branch,
                " ".join(s.topics), " ".join(s.domains), s.slug,
            ]).lower()
            if q in haystack:
                results.append(s)
        return results

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
        """Rebuild the option list, respecting collapsed state."""
        option_list = self.query_one("#session-options", OptionList)
        option_list.clear_options()
        self._id_map.clear()
        self._group_map.clear()

        filtered = self._filtered()
        self._grouped_data = self._group_sessions(filtered)
        self._group_labels = [label for label, _ in self._grouped_data]

        counter = 0
        for label, items in self._grouped_data:
            is_collapsed = label in self._collapsed
            arrow = "▶" if is_collapsed else "▼"

            # Group header — selectable so cursor can land on it
            hdr_id = f"{_HDR}{counter}"
            self._group_map[hdr_id] = label
            header_text = Text(f"{arrow} {label} ({len(items)})", style="bold #f0f6fc")
            option_list.add_option(Option(header_text, id=hdr_id))

            if not is_collapsed:
                items_sorted = sorted(items, key=lambda s: (not s.is_active, s.started_at))
                for s in items_sorted:
                    counter += 1
                    opt_id = f"{_SES}{counter}"
                    self._id_map[opt_id] = s.session_id
                    self._group_map[opt_id] = label

                    dot = "●" if s.is_active else "○"
                    dot_style = "green" if s.is_active else "#484f58"
                    name = s.display_name[:45]
                    meta = f"{s.project_short} · {s.duration_display}"
                    tags = " ".join(s.domains[:2]) if s.domains else ""

                    card = Text()
                    card.append(f"{dot} ", style=dot_style)
                    card.append(f"{name}\n", style="#c9d1d9")
                    card.append(f"  {meta}", style="#8b949e")
                    if tags:
                        card.append(f"\n  {tags}", style="#484f58")

                    option_list.add_option(Option(card, id=opt_id))

            counter += 1

    def toggle_group(self, collapse: bool) -> None:
        """Collapse or expand the group the cursor is currently on/in.

        Args:
            collapse: True to collapse (A/left), False to expand (D/right).
        """
        option_list = self.query_one("#session-options", OptionList)
        highlighted = option_list.highlighted
        if highlighted is None:
            return

        # Get the option at the cursor
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
            # Try to re-highlight the group header we just toggled
            self._focus_group_header(group_label, option_list)

    def _focus_group_header(self, label: str, option_list: OptionList) -> None:
        """Move the cursor to a specific group's header."""
        for opt_id, grp in self._group_map.items():
            if grp == label and opt_id.startswith(_HDR):
                # Find the index of this option
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

    def watch_filter_text(self, _old: str, _new: str) -> None:
        if self._sessions:
            self._rebuild()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Forward session selection to the app, or toggle group on header."""
        opt_id = event.option.id or ""
        if opt_id.startswith(_HDR):
            # Toggle collapse on Enter/click
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
