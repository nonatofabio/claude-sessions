"""Main Textual application for the Sessions TUI."""

from __future__ import annotations

import subprocess
from collections import defaultdict
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.events import Key
from textual.widgets import Input, OptionList

from .active import detect_active_sessions, match_active_to_sessions
from .cache import load_or_rebuild
from .models import SessionSummary
from .widgets.detail_pane import DetailPane
from .widgets.search_bar import SearchBar
from .widgets.session_list import SessionList, SessionSelected
from .widgets.status_bar import StatusBar


class SessionsTUI(App):
    """Terminal UI for browsing Claude Code sessions."""

    TITLE = "Sessions TUI"
    CSS_PATH = "styles/app.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("slash", "focus_search", "Search", key_display="/"),
        Binding("escape", "unfocus_search", "Clear"),
        Binding("r", "refresh", "Refresh"),
        Binding("1", "dimension('project')", "Project"),
        Binding("2", "dimension('topic')", "Topic"),
        Binding("3", "dimension('domain')", "Domain"),
        Binding("4", "dimension('date')", "Date"),
        Binding("5", "dimension('branch')", "Branch"),
        Binding("tab", "focus_next", "Next pane"),
    ]

    def __init__(
        self,
        projects_dir: Path | None = None,
        cache_path: Path | None = None,
        force_refresh: bool = False,
        detect_active: bool = True,
        demo_mode: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.projects_dir = projects_dir or Path.home() / ".claude" / "projects"
        self.cache_path = cache_path or Path.home() / ".claude" / "sessions_tui_cache.json"
        self.force_refresh = force_refresh
        self.detect_active_flag = detect_active
        self.demo_mode = demo_mode
        self._sessions: list[SessionSummary] = []
        self._sessions_by_id: dict[str, SessionSummary] = {}

    def compose(self) -> ComposeResult:
        yield SearchBar()
        with Horizontal(id="main-content"):
            yield SessionList(id="session-list-pane")
            yield DetailPane(id="detail-pane")
        yield StatusBar(id="status-bar")

    def on_mount(self) -> None:
        """Start loading data in the background."""
        self.load_sessions()

    # --- WASD navigation via on_key (bypasses bindings so it works with Input) ---

    def on_key(self, event: Key) -> None:
        """Handle WASD + arrow keys — only when search is NOT focused."""
        focused = self.focused
        in_search = isinstance(focused, Input) and focused.id == "search-input"

        if in_search:
            return

        match event.key:
            # W/S — navigate up/down in session list
            case "w":
                ol = self.query_one("#session-options", OptionList)
                ol.focus()
                ol.action_cursor_up()
                event.prevent_default()
                event.stop()
            case "s":
                ol = self.query_one("#session-options", OptionList)
                ol.focus()
                ol.action_cursor_down()
                event.prevent_default()
                event.stop()

            # A / Left — collapse current group
            case "a" | "left":
                sl = self.query_one("#session-list-pane", SessionList)
                sl.toggle_group(collapse=True)
                event.prevent_default()
                event.stop()

            # D / Right — expand current group
            case "d" | "right":
                sl = self.query_one("#session-list-pane", SessionList)
                sl.toggle_group(collapse=False)
                event.prevent_default()
                event.stop()

            # O / Enter — open session in new terminal
            case "o" | "enter":
                self._open_highlighted_session()
                event.prevent_default()
                event.stop()

            # Arrow up/down — scroll the detail pane
            case "up":
                dp = self.query_one("#detail-pane", DetailPane)
                dp.scroll_up(animate=False)
                event.prevent_default()
                event.stop()
            case "down":
                dp = self.query_one("#detail-pane", DetailPane)
                dp.scroll_down(animate=False)
                event.prevent_default()
                event.stop()

    # --- Data loading ---

    def load_sessions(self) -> None:
        """Load sessions in a background thread worker."""
        self.run_worker(self._load_sync, thread=True, name="load-sessions", exclusive=True)

    def _load_sync(self) -> list[SessionSummary]:
        """Sync function run in a thread: parse/load sessions from cache."""
        if self.demo_mode:
            from .demo import generate_demo_sessions
            return generate_demo_sessions()

        sessions = load_or_rebuild(
            self.projects_dir, self.cache_path, self.force_refresh,
        )

        if self.detect_active_flag:
            active = detect_active_sessions()
            cwd_map: dict[str, list[str]] = defaultdict(list)
            for s in sessions:
                if s.cwd:
                    cwd_map[s.cwd].append(s.session_id)
            active_ids = match_active_to_sessions(active, cwd_map)
            for s in sessions:
                s.is_active = s.session_id in active_ids

        return sessions

    def on_worker_state_changed(self, event) -> None:
        """Handle worker completion."""
        if event.worker.name != "load-sessions":
            return
        state_name = str(event.state).split(".")[-1].upper()
        if state_name == "SUCCESS":
            sessions = event.worker.result
            if sessions:
                self._sessions = sessions
                self._sessions_by_id = {s.session_id: s for s in sessions}
                self._update_ui()

    def _update_ui(self) -> None:
        """Push session data to all widgets."""
        session_list = self.query_one("#session-list-pane", SessionList)
        session_list.set_sessions(self._sessions)

        active_count = sum(1 for s in self._sessions if s.is_active)
        status = self.query_one("#status-bar", StatusBar)
        status.update_stats(len(self._sessions), active_count)

        # Auto-select first session and focus the list
        if self._sessions:
            detail = self.query_one("#detail-pane", DetailPane)
            detail.show_session(self._sessions[0])

        # Focus the session list so WASD works immediately
        self.query_one("#session-options", OptionList).focus()
        self.notify(f"Loaded {len(self._sessions)} sessions", timeout=3)

    # --- Message handlers ---

    def on_session_selected(self, message: SessionSelected) -> None:
        """Handle session selection from the list."""
        session = self._sessions_by_id.get(message.session_id)
        if session:
            self.query_one("#detail-pane", DetailPane).show_session(session)

    def on_search_bar_search_changed(self, message: SearchBar.SearchChanged) -> None:
        """Handle search text changes."""
        session_list = self.query_one("#session-list-pane", SessionList)
        session_list.filter_text = message.value
        filtered = len(session_list._filtered())
        active_count = sum(1 for s in self._sessions if s.is_active)
        self.query_one("#status-bar", StatusBar).update_stats(
            len(self._sessions), active_count, filtered,
        )

    def on_search_bar_dimension_changed(self, message: SearchBar.DimensionChanged) -> None:
        """Handle dimension tab changes."""
        self.query_one("#session-list-pane", SessionList).dimension = message.dimension

    # --- Actions ---

    def action_focus_search(self) -> None:
        self.query_one(SearchBar).focus_search()

    def action_unfocus_search(self) -> None:
        """Escape — clear search, reset filter, return focus to session list."""
        self.query_one(SearchBar).clear_search()
        # Explicitly reset the filter in case the Input.Changed event doesn't fire
        session_list = self.query_one("#session-list-pane", SessionList)
        session_list.filter_text = ""
        active_count = sum(1 for s in self._sessions if s.is_active)
        self.query_one("#status-bar", StatusBar).update_stats(
            len(self._sessions), active_count,
        )
        self.query_one("#session-options", OptionList).focus()

    def action_refresh(self) -> None:
        self.force_refresh = True
        self.load_sessions()
        self.force_refresh = False

    def action_dimension(self, dim: str) -> None:
        self.query_one(SearchBar).set_dimension(dim)
        self.query_one("#session-list-pane", SessionList).dimension = dim

    def _open_highlighted_session(self) -> None:
        """Open the highlighted session in a new Terminal window via claude --resume."""
        sl = self.query_one("#session-list-pane", SessionList)
        session_id = sl.get_highlighted_session_id()
        if not session_id:
            return

        session = self._sessions_by_id.get(session_id)
        if not session:
            return

        cwd = session.cwd or str(Path.home())
        name = session.display_name[:50]

        # Build the shell command
        cmd = f"cd {_shell_quote(cwd)} && claude --resume {session_id}"

        # Open in a new Terminal.app window
        applescript = (
            'tell application "Terminal"\n'
            "    activate\n"
            f'    do script "{_applescript_escape(cmd)}"\n'
            "end tell"
        )
        try:
            subprocess.run(["osascript", "-e", applescript], capture_output=True, timeout=5)
            self.notify(f"Opened: {name}", timeout=3)
        except Exception as exc:
            self.notify(f"Failed to open terminal: {exc}", severity="error", timeout=5)


def _shell_quote(s: str) -> str:
    """Quote a string for safe use in a shell command."""
    return "'" + s.replace("'", "'\\''") + "'"


def _applescript_escape(s: str) -> str:
    """Escape a string for embedding inside AppleScript double quotes."""
    return s.replace("\\", "\\\\").replace('"', '\\"')
