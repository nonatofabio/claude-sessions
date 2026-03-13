"""Search bar with text input and dimension selector tabs."""

from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Input, OptionList


DIMENSIONS = [
    ("1:Project", "project"),
    ("2:Topic", "topic"),
    ("3:Domain", "domain"),
    ("4:Date", "date"),
    ("5:Branch", "branch"),
]


class SearchBar(Widget):
    """Top bar with search input and dimension tabs."""

    @dataclass
    class SearchChanged(Message):
        value: str

    @dataclass
    class DimensionChanged(Message):
        dimension: str

    def compose(self) -> ComposeResult:
        with Horizontal(id="search-bar"):
            yield Input(placeholder="Search sessions...", id="search-input")
            for label, dim in DIMENSIONS:
                btn = Button(label, id=f"dim-{dim}", classes="dim-button")
                if dim == "project":
                    btn.add_class("-active")
                yield btn

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search-input":
            self.post_message(self.SearchChanged(event.value))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter in search — commit the filter and jump to the session list."""
        if event.input.id == "search-input":
            # Focus the session option list so user can immediately navigate
            try:
                self.app.query_one("#session-options", OptionList).focus()
            except Exception:
                pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id.startswith("dim-"):
            dim = btn_id[4:]
            # Update active state on all dim buttons
            for _, d in DIMENSIONS:
                btn = self.query_one(f"#dim-{d}", Button)
                if d == dim:
                    btn.add_class("-active")
                else:
                    btn.remove_class("-active")
            self.post_message(self.DimensionChanged(dim))

    def set_dimension(self, dim: str) -> None:
        """Programmatically set the active dimension."""
        for _, d in DIMENSIONS:
            btn = self.query_one(f"#dim-{d}", Button)
            if d == dim:
                btn.add_class("-active")
            else:
                btn.remove_class("-active")

    def focus_search(self) -> None:
        """Focus the search input."""
        self.query_one("#search-input", Input).focus()

    def clear_search(self) -> None:
        """Clear the search input."""
        inp = self.query_one("#search-input", Input)
        inp.value = ""
