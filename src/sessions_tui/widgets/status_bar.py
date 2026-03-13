"""Bottom status bar showing session stats and key hints."""

from __future__ import annotations

from textual.widgets import Static


class StatusBar(Static):
    """Footer bar with session count, active count, and keybinding hints."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._total = 0
        self._active = 0
        self._filtered = 0

    def update_stats(self, total: int, active: int, filtered: int | None = None) -> None:
        """Update the displayed stats."""
        self._total = total
        self._active = active
        self._filtered = filtered if filtered is not None else total
        self._refresh_text()

    def _refresh_text(self) -> None:
        filtered_text = f" ({self._filtered} shown)" if self._filtered != self._total else ""
        self.update(
            f" {self._total} sessions{filtered_text} │ "
            f"[green]{self._active}[/] active │ "
            f"[#58a6ff]W/S[/] list  "
            f"[#58a6ff]A/D[/] fold  "
            f"[#58a6ff]arrows[/] detail  "
            f"[#3fb950]o[/] open  "
            f"[#8b949e]/[/] search  "
            f"[#8b949e]1-5[/] dim  "
            f"[#8b949e]q[/] quit"
        )
