"""Configs list — browse and manage saved config files from both locations."""
from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.message import Message
from textual.widgets import Button, DataTable, Static


class ConfigsList(Vertical):
    """Browse config files from ~/Documents/dissenter/configs/ and the current directory."""

    class UseAsTemplate(Message):
        """Emitted when user clicks 'Use as template' — carries the config file path."""
        def __init__(self, path: Path) -> None:
            self.path = path
            super().__init__()

    DEFAULT_CSS = """
    ConfigsList {
        height: 1fr;
    }
    ConfigsList #cl-tables {
        height: auto;
        max-height: 50%;
        padding: 1 4 0 4;
    }
    ConfigsList .section-header {
        text-style: bold;
        margin-top: 1;
        margin-bottom: 0;
    }
    ConfigsList .section-path {
        color: $text-muted;
        margin-bottom: 1;
    }
    ConfigsList DataTable {
        height: auto;
        max-height: 8;
        margin-bottom: 1;
    }
    ConfigsList #cl-preview-scroll {
        height: 1fr;
        padding: 0 4;
        border-top: solid $primary-background;
    }
    ConfigsList #cl-preview-header {
        text-style: bold;
        margin-top: 1;
        margin-bottom: 0;
    }
    ConfigsList #cl-preview {
        padding: 1 2;
    }
    ConfigsList #cl-hint {
        padding: 0 4;
        margin-top: 1;
    }
    ConfigsList #cl-actions-row1 {
        height: auto;
        padding: 0 4;
    }
    ConfigsList #cl-actions-row2 {
        height: auto;
        padding: 0 4;
    }
    ConfigsList .cl-btn {
        margin-right: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="cl-tables"):
            yield Static("Saved configs", classes="section-header")
            yield Static("", id="cl-saved-path", classes="section-path")
            yield DataTable(id="cl-saved-table")

            yield Static("Current directory", classes="section-header")
            yield Static("", id="cl-cwd-path", classes="section-path")
            yield DataTable(id="cl-cwd-table")

        yield Static("[dim]Click a row to preview. Double-click or Enter to edit.[/dim]", id="cl-hint", markup=True)

        with VerticalScroll(id="cl-preview-scroll"):
            yield Static("", id="cl-preview-header")
            yield Static("", id="cl-preview")

        with Horizontal(id="cl-actions-row1"):
            yield Button("Use as template", id="cl-template", variant="success", classes="cl-btn")
            yield Button("Edit in editor", id="cl-edit", variant="primary", classes="cl-btn")
            yield Button("Delete selected", id="cl-delete", variant="error", classes="cl-btn")
        with Horizontal(id="cl-actions-row2"):
            yield Button("Open saved folder", id="cl-open-folder", variant="warning", classes="cl-btn")
            yield Button("Refresh", id="cl-refresh", variant="default", classes="cl-btn")

    def on_mount(self) -> None:
        for table_id in ("#cl-saved-table", "#cl-cwd-table"):
            table = self.query_one(table_id, DataTable)
            table.add_columns("Name", "Size")
            table.cursor_type = "row"
        self.load_configs()

    def load_configs(self) -> None:
        from dissenter.paths import configs_dir

        self._saved_paths: list[Path] = []
        self._cwd_paths: list[Path] = []
        self._last_selected: Path | None = None

        # Section 1: ~/Documents/dissenter/configs/
        cfg_dir = configs_dir()
        saved_table = self.query_one("#cl-saved-table", DataTable)
        saved_table.clear()
        self.query_one("#cl-saved-path", Static).update(f"[dim]{cfg_dir}[/dim]")

        if cfg_dir.exists():
            for f in sorted(cfg_dir.glob("*.toml")):
                if f.name.startswith("_"):
                    continue
                size = f.stat().st_size
                size_str = f"{size} B" if size < 1024 else f"{size / 1024:.1f} KB"
                saved_table.add_row(f.name, size_str)
                self._saved_paths.append(f)

        # Section 2: Current working directory
        cwd = Path.cwd()
        cwd_table = self.query_one("#cl-cwd-table", DataTable)
        cwd_table.clear()
        self.query_one("#cl-cwd-path", Static).update(f"[dim]{cwd}[/dim]")

        for f in sorted(cwd.glob("dissenter*.toml")):
            size = f.stat().st_size
            size_str = f"{size} B" if size < 1024 else f"{size / 1024:.1f} KB"
            cwd_table.add_row(f.name, size_str)
            self._cwd_paths.append(f)

        # Clear preview
        self.query_one("#cl-preview-header", Static).update("")
        self.query_one("#cl-preview", Static).update("")

    def _resolve_path_from_event(self, event: DataTable.RowSelected) -> Path | None:
        table = event.data_table
        if table.id == "cl-saved-table":
            paths = self._saved_paths
        elif table.id == "cl-cwd-table":
            paths = self._cwd_paths
        else:
            return None
        idx = event.cursor_row
        if 0 <= idx < len(paths):
            return paths[idx]
        return None

    def _get_selected_path(self) -> Path | None:
        """Return the last-selected path, or fall back to focused table cursor."""
        if self._last_selected and self._last_selected.exists():
            return self._last_selected

        for table_id, paths in (
            ("#cl-saved-table", getattr(self, "_saved_paths", [])),
            ("#cl-cwd-table", getattr(self, "_cwd_paths", [])),
        ):
            table = self.query_one(table_id, DataTable)
            try:
                idx = table.cursor_row
                if table.has_focus and 0 <= idx < len(paths):
                    return paths[idx]
            except Exception:
                pass
        return None

    def _show_preview(self, path: Path) -> None:
        """Load a config file's contents into the preview area."""
        self._last_selected = path
        header = self.query_one("#cl-preview-header", Static)
        preview = self.query_one("#cl-preview", Static)
        header.update(f"[bold]{path.name}[/bold]  [dim]{path.parent}[/dim]")
        try:
            contents = path.read_text(encoding="utf-8")
        except Exception as e:
            contents = f"[red]Error reading file: {e}[/red]"
        preview.update(contents)

    def _open_in_editor(self, path: Path) -> None:
        """Open the given config in the OS text editor."""
        import subprocess
        import sys
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-t", str(path)])
        elif sys.platform == "win32":
            subprocess.Popen(["notepad", str(path)])
        else:
            editor = __import__("os").environ.get("EDITOR", "xdg-open")
            subprocess.Popen([editor, str(path)])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cl-template":
            path = self._get_selected_path()
            if path and path.exists():
                self.post_message(self.UseAsTemplate(path))
            else:
                self.app.notify("Select a config first", severity="warning")
        elif event.button.id == "cl-delete":
            path = self._get_selected_path()
            if path and path.exists():
                path.unlink()
                self.app.notify(f"Deleted: {path.name}", title="Config removed")
                self.load_configs()
            else:
                self.app.notify("Select a row first", severity="warning")
        elif event.button.id == "cl-edit":
            path = self._get_selected_path()
            if path and path.exists():
                self._open_in_editor(path)
            else:
                self.app.notify("Select a row first", severity="warning")
        elif event.button.id == "cl-open-folder":
            from dissenter.paths import configs_dir, open_in_finder
            d = configs_dir()
            if d.exists():
                open_in_finder(d)
            else:
                self.app.notify("Configs folder doesn't exist yet.", severity="warning")
        elif event.button.id == "cl-refresh":
            self.load_configs()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Show config preview when a row is highlighted (single click/arrow keys)."""
        table = event.data_table
        if table.id == "cl-saved-table":
            paths = self._saved_paths
        elif table.id == "cl-cwd-table":
            paths = self._cwd_paths
        else:
            return
        idx = event.cursor_row
        if 0 <= idx < len(paths):
            self._show_preview(paths[idx])

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Open config in editor on Enter/double-click."""
        path = self._resolve_path_from_event(event)
        if path:
            self._open_in_editor(path)
