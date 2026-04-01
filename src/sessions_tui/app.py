"""Main Textual application for the Sessions TUI."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
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
from .search import SessionSearchIndex
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
        search_top_k: int = 25,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.projects_dir = projects_dir or Path.home() / ".claude" / "projects"
        self.cache_path = cache_path or Path.home() / ".claude" / "sessions_tui_cache.json"
        self.force_refresh = force_refresh
        self.detect_active_flag = detect_active
        self.demo_mode = demo_mode
        self.search_top_k = search_top_k
        self._sessions: list[SessionSummary] = []
        self._sessions_by_id: dict[str, SessionSummary] = {}
        self._search_index = SessionSearchIndex()

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

    def _load_sync(self) -> tuple[list[SessionSummary], bool]:
        """Sync function run in a thread: load sessions + warm up semantic search."""
        import warnings

        if self.demo_mode:
            from .demo import generate_demo_sessions
            sessions = generate_demo_sessions()
        else:
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

        # Build search index + warm up semantic embeddings in the same thread
        self._search_index.build(sessions)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                semantic_ok = self._search_index._ensure_semantic()
        except Exception:
            semantic_ok = False

        return sessions, semantic_ok is True

    def on_worker_state_changed(self, event) -> None:
        """Handle load-sessions worker completion."""
        if event.worker.name != "load-sessions":
            return
        state_name = str(event.state).split(".")[-1].upper()
        if state_name == "SUCCESS" and event.worker.result:
            sessions, semantic_ok = event.worker.result
            self._sessions = sessions
            self._sessions_by_id = {s.session_id: s for s in sessions}
            self._update_ui(semantic_ok)

    def _update_ui(self, semantic_ok: bool = False) -> None:
        """Push session data to all widgets."""
        session_list = self.query_one("#session-list-pane", SessionList)
        session_list.set_sessions(self._sessions)

        active_count = sum(1 for s in self._sessions if s.is_active)
        status = self.query_one("#status-bar", StatusBar)
        status.update_stats(len(self._sessions), active_count)

        if self._sessions:
            detail = self.query_one("#detail-pane", DetailPane)
            detail.show_session(self._sessions[0])

        self.query_one("#session-options", OptionList).focus()

        sem_label = " + semantic" if semantic_ok else ""
        self.notify(f"Loaded {len(self._sessions)} sessions{sem_label}", timeout=3)

    # --- Message handlers ---

    def on_session_selected(self, message: SessionSelected) -> None:
        """Handle session selection from the list."""
        session = self._sessions_by_id.get(message.session_id)
        if session:
            self.query_one("#detail-pane", DetailPane).show_session(session)

    def on_search_bar_search_changed(self, message: SearchBar.SearchChanged) -> None:
        """Handle search text changes with hybrid BM25+semantic ranking."""
        session_list = self.query_one("#session-list-pane", SessionList)
        query = message.value.strip()

        if not query:
            session_list.set_filtered(self._sessions)
        else:
            results = self._search_index.search(query, top_k=self.search_top_k)
            ranked_sessions = [s for s, score in results]
            session_list.set_filtered(ranked_sessions)

        active_count = sum(1 for s in self._sessions if s.is_active)
        self.query_one("#status-bar", StatusBar).update_stats(
            len(self._sessions), active_count, len(session_list._display_sessions),
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
        session_list = self.query_one("#session-list-pane", SessionList)
        session_list.set_filtered(self._sessions)
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
        """Open the highlighted session in a new terminal window via claude --resume."""
        sl = self.query_one("#session-list-pane", SessionList)
        session_id = sl.get_highlighted_session_id()
        if not session_id:
            return

        session = self._sessions_by_id.get(session_id)
        if not session:
            return

        cwd = session.cwd or str(Path.home())
        name = session.display_name[:50]

        try:
            if sys.platform == "darwin":
                _open_session_macos(session_id, cwd)
            elif sys.platform == "win32":
                _open_session_windows(session_id, cwd)
            else:
                _open_session_linux(session_id, cwd)
            self.notify(f"Opened: {name}", timeout=3)
        except Exception as exc:
            self.notify(f"Failed to open terminal: {exc}", severity="error", timeout=5)


# ---------------------------------------------------------------------------
# Platform-specific terminal launchers
# ---------------------------------------------------------------------------

def _open_session_macos(session_id: str, cwd: str) -> None:
    """Open a session in a new Terminal.app window on macOS."""
    cmd = f"cd {_shell_quote(cwd)} && claude --resume {session_id}"
    applescript = (
        'tell application "Terminal"\n'
        "    activate\n"
        f'    do script "{_applescript_escape(cmd)}"\n'
        "end tell"
    )
    subprocess.run(["osascript", "-e", applescript], capture_output=True, timeout=5)


def _open_session_windows(session_id: str, cwd: str) -> None:
    """Open a session in a new terminal window on Windows."""
    resume_cmd = f"claude --resume {session_id}"
    if shutil.which("wt"):
        # Windows Terminal — open new tab in the working directory
        subprocess.Popen(["wt", "-d", cwd, "cmd", "/k", resume_cmd])
    else:
        # Fallback to classic cmd.exe in a new window
        # Empty "" after 'start' is the window title (required when command is quoted)
        subprocess.Popen(
            ["cmd", "/c", "start", "", "cmd", "/k",
             f"cd /d {_win_quote(cwd)} && {resume_cmd}"],
        )


def _open_session_linux(session_id: str, cwd: str) -> None:
    """Open a session in a new terminal window on Linux."""
    shell_cmd = f"cd {_shell_quote(cwd)} && claude --resume {session_id}; exec $SHELL"

    # Honour $TERMINAL env var first
    env_terminal = os.environ.get("TERMINAL")
    if env_terminal and shutil.which(env_terminal):
        subprocess.Popen([env_terminal, "-e", "bash", "-c", shell_cmd])
        return

    # Try common terminal emulators in order of popularity.
    # Each entry: (binary, [prefix args]) — "bash", "-c", shell_cmd is appended.
    terminals: list[tuple[str, list[str]]] = [
        ("gnome-terminal", ["gnome-terminal", "--"]),
        ("konsole",        ["konsole", "-e"]),
        ("xfce4-terminal", ["xfce4-terminal", "-x"]),
        ("alacritty",      ["alacritty", "-e"]),
        ("kitty",          ["kitty"]),
        ("wezterm",        ["wezterm", "start", "--"]),
        ("x-terminal-emulator", ["x-terminal-emulator", "-e"]),
        ("xterm",          ["xterm", "-e"]),
    ]

    for binary, prefix in terminals:
        if shutil.which(binary):
            subprocess.Popen([*prefix, "bash", "-c", shell_cmd])
            return

    raise RuntimeError(
        "No supported terminal emulator found. "
        "Set $TERMINAL or install one of: "
        "gnome-terminal, konsole, alacritty, kitty, wezterm, xterm"
    )


# ---------------------------------------------------------------------------
# Shell quoting helpers
# ---------------------------------------------------------------------------

def _shell_quote(s: str) -> str:
    """Quote a string for safe use in a POSIX shell command."""
    return "'" + s.replace("'", "'\\''") + "'"


def _win_quote(s: str) -> str:
    """Quote a string for safe use in a Windows cmd.exe command.

    Wraps the string in double quotes after escaping characters that
    have special meaning inside cmd.exe double-quoted strings.
    """
    # Escape existing double quotes, then the cmd.exe metacharacters
    # that remain active even inside double quotes.
    s = s.replace('"', '""')
    for ch in "%!^":
        s = s.replace(ch, f"^{ch}")
    return f'"{s}"'


def _applescript_escape(s: str) -> str:
    """Escape a string for embedding inside AppleScript double quotes."""
    return s.replace("\\", "\\\\").replace('"', '\\"')
