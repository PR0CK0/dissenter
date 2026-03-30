"""History table — browse past decisions from the SQLite database."""

from __future__ import annotations

from textual.message import Message
from textual.widgets import DataTable


class HistoryTable(DataTable):
    """Browse past decisions from the SQLite database."""

    class Selected(Message):
        """Emitted when a row is selected, carrying the run_id."""

        def __init__(self, run_id: int) -> None:
            self.run_id = run_id
            super().__init__()

    def on_mount(self) -> None:
        self.add_columns("#", "Date", "Question")
        self.cursor_type = "row"

    def load_runs(self, search: str | None = None, limit: int = 50) -> None:
        from dissenter.db import list_runs

        self.clear()
        self._run_ids: list[int] = []

        runs = list_runs(limit=limit, search=search)
        for run in runs:
            question = run["question"]
            if len(question) > 60:
                question = question[:57] + "..."
            ts = run["timestamp"][:16]  # trim to YYYY-MM-DD HH:MM
            self.add_row(str(run["id"]), ts, question)
            self._run_ids.append(run["id"])

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Fires on Enter or double-click."""
        row_index = event.cursor_row
        if hasattr(self, "_run_ids") and 0 <= row_index < len(self._run_ids):
            self.post_message(self.Selected(self._run_ids[row_index]))

    def on_click(self, event) -> None:
        """Also open decision on single click after a short delay."""
        # Let the DataTable handle the click first (moves cursor),
        # then post Selected for the now-highlighted row
        self.set_timer(0.1, self._emit_for_cursor)

    def _emit_for_cursor(self) -> None:
        try:
            row_index = self.cursor_row
            if hasattr(self, "_run_ids") and 0 <= row_index < len(self._run_ids):
                self.post_message(self.Selected(self._run_ids[row_index]))
        except Exception:
            pass
