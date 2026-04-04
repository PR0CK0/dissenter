"""History table — browse past decisions from the SQLite database."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, DataTable, Static


class HistoryTable(Vertical):
    """Browse past decisions from the SQLite database."""

    DEFAULT_CSS = """
    HistoryTable {
        height: 1fr;
    }
    HistoryTable #ht-table {
        height: 1fr;
    }
    HistoryTable #ht-actions {
        height: auto;
        padding: 1 2;
    }
    HistoryTable #ht-actions Button {
        margin-right: 1;
    }
    """

    class Selected(Message):
        """Emitted when a row is selected, carrying the run_id."""

        def __init__(self, run_id: int) -> None:
            self.run_id = run_id
            super().__init__()

    def compose(self) -> ComposeResult:
        yield DataTable(id="ht-table")
        with Horizontal(id="ht-actions"):
            yield Button("Delete selected", id="ht-delete", variant="error")

    def on_mount(self) -> None:
        table = self.query_one("#ht-table", DataTable)
        table.add_columns("#", "Date", "Question")
        table.cursor_type = "row"

    def load_runs(self, search: str | None = None, limit: int = 50) -> None:
        from dissenter.db import list_runs

        table = self.query_one("#ht-table", DataTable)
        table.clear()
        self._run_ids: list[int] = []

        runs = list_runs(limit=limit, search=search)
        for run in runs:
            question = run["question"]
            if len(question) > 60:
                question = question[:57] + "..."
            ts = run["timestamp"][:16]
            table.add_row(str(run["id"]), ts, question)
            self._run_ids.append(run["id"])

    def _get_selected_run_id(self) -> int | None:
        table = self.query_one("#ht-table", DataTable)
        try:
            idx = table.cursor_row
            if hasattr(self, "_run_ids") and 0 <= idx < len(self._run_ids):
                return self._run_ids[idx]
        except Exception:
            pass
        return None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ht-delete":
            run_id = self._get_selected_run_id()
            if run_id is None:
                self.app.notify("Select a row first", severity="warning")
                return
            from dissenter.db import delete_run
            delete_run(run_id)
            self.app.notify(f"Deleted decision #{run_id}", title="Removed")
            self.load_runs()
            # Refresh sidebar history too
            try:
                from .sidebar import Sidebar
                self.app.query_one("#sidebar", Sidebar).refresh_history()
            except Exception:
                pass

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Fires on Enter or double-click."""
        table = self.query_one("#ht-table", DataTable)
        row_index = event.cursor_row
        if hasattr(self, "_run_ids") and 0 <= row_index < len(self._run_ids):
            self.post_message(self.Selected(self._run_ids[row_index]))

    def on_click(self, event) -> None:
        """Also open decision on single click after a short delay."""
        self.set_timer(0.1, self._emit_for_cursor)

    def _emit_for_cursor(self) -> None:
        try:
            table = self.query_one("#ht-table", DataTable)
            row_index = table.cursor_row
            if hasattr(self, "_run_ids") and 0 <= row_index < len(self._run_ids):
                self.post_message(self.Selected(self._run_ids[row_index]))
        except Exception:
            pass
