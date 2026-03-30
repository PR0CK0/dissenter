"""Configs list — browse and manage saved config files from both locations."""
from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Button, DataTable, Static


class ConfigsList(Vertical):
    """Browse config files from ~/Documents/dissenter/configs/ and the current directory."""

    DEFAULT_CSS = """
    ConfigsList {
        padding: 2 4;
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
        max-height: 12;
        margin-bottom: 1;
    }
    ConfigsList #cl-actions {
        height: 3;
        margin-top: 1;
    }
    ConfigsList #cl-actions Button {
        margin-right: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Saved configs", classes="section-header")
        yield Static("", id="cl-saved-path", classes="section-path")
        yield DataTable(id="cl-saved-table")

        yield Static("Current directory", classes="section-header")
        yield Static("", id="cl-cwd-path", classes="section-path")
        yield DataTable(id="cl-cwd-table")

        yield Static("[dim]Click a row to edit in your text editor.[/dim]", markup=True)
        with Horizontal(id="cl-actions"):
            yield Button("Delete selected", id="cl-delete", variant="error")
            yield Button("Open saved folder", id="cl-open-folder", variant="warning")
            yield Button("Refresh", id="cl-refresh", variant="default")

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

    def _get_selected_path(self) -> Path | None:
        """Return the path of whichever table row was last selected."""
        # Check saved table first
        saved_table = self.query_one("#cl-saved-table", DataTable)
        try:
            idx = saved_table.cursor_row
            if saved_table.has_focus and 0 <= idx < len(self._saved_paths):
                return self._saved_paths[idx]
        except Exception:
            pass

        # Then cwd table
        cwd_table = self.query_one("#cl-cwd-table", DataTable)
        try:
            idx = cwd_table.cursor_row
            if cwd_table.has_focus and 0 <= idx < len(self._cwd_paths):
                return self._cwd_paths[idx]
        except Exception:
            pass

        return None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cl-delete":
            path = self._get_selected_path()
            if path and path.exists():
                path.unlink()
                self.app.notify(f"Deleted: {path.name}", title="Config removed")
                self.load_configs()
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

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Open the config file in the OS text editor."""
        # Determine which table fired the event
        table = event.data_table
        if table.id == "cl-saved-table":
            paths = self._saved_paths
        elif table.id == "cl-cwd-table":
            paths = self._cwd_paths
        else:
            return

        idx = event.cursor_row
        if 0 <= idx < len(paths):
            import subprocess
            import sys
            path = paths[idx]
            if sys.platform == "darwin":
                subprocess.Popen(["open", "-t", str(path)])
            elif sys.platform == "win32":
                subprocess.Popen(["notepad", str(path)])
            else:
                editor = __import__("os").environ.get("EDITOR", "xdg-open")
                subprocess.Popen([editor, str(path)])
