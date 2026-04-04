"""Decision viewer — view a completed decision with Prompt/ADR tabs and action buttons."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Button, MarkdownViewer, Static, TabbedContent, TabPane


class DecisionViewer(Vertical):
    """View a completed decision with Prompt and ADR tabs plus action buttons."""

    DEFAULT_CSS = """
    DecisionViewer {
        height: 1fr;
    }

    DecisionViewer #dv-header {
        height: 1;
        padding: 0 1;
        background: $surface;
    }

    DecisionViewer #dv-path {
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }

    DecisionViewer #dv-tabs {
        height: 1fr;
    }

    DecisionViewer #dv-buttons {
        height: 3;
        align: center middle;
        padding: 0 1;
    }

    DecisionViewer #dv-buttons Button {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("No decision loaded", id="dv-header")
        yield Static("", id="dv-path")
        with TabbedContent(id="dv-tabs"):
            with TabPane("Prompt", id="dv-tab-prompt"):
                yield Static("", id="dv-prompt-text")
            with TabPane("ADR", id="dv-tab-adr"):
                yield MarkdownViewer("", id="dv-markdown", show_table_of_contents=False)
            with TabPane("Config", id="dv-tab-config"):
                with VerticalScroll(id="dv-config-scroll"):
                    yield Static("", id="dv-config-text")
        with Horizontal(id="dv-buttons"):
            yield Button("Open folder", id="dv-open", variant="warning")
            yield Button("Continue from this", id="dv-continue", variant="primary")
            yield Button("Re-run", id="dv-rerun", variant="default")
            yield Button("Back", id="dv-back", variant="default")

    def load_decision(self, run_id: int) -> None:
        from dissenter.db import get_run

        self._run_id = run_id
        self._run_dir = None

        run = get_run(run_id)
        if run is None:
            header = self.query_one("#dv-header", Static)
            header.update(f"[red]Decision #{run_id} not found[/red]")
            return

        ts = run["timestamp"][:16]
        header = self.query_one("#dv-header", Static)
        header.update(f"[bold]Decision #{run['id']}[/bold]  [dim]{ts}[/dim]")

        path_label = self.query_one("#dv-path", Static)
        if run.get("run_dir"):
            self._run_dir = run["run_dir"]
            path_label.update(f"[dim]{run['run_dir']}[/dim]")
        else:
            path_label.update("")

        # Prompt tab
        prompt_widget = self.query_one("#dv-prompt-text", Static)
        prompt_widget.update(run.get("question", "(no prompt stored)"))

        # ADR tab
        md_viewer = self.query_one("#dv-markdown", MarkdownViewer)
        md_viewer.document.update(run["decision_md"])

        # Config tab
        config_widget = self.query_one("#dv-config-text", Static)
        config_toml = run.get("config_toml", "(no config stored)")
        config_widget.update(config_toml)

    class RerunRequested(Message):
        """Emitted when user clicks Re-run."""
        def __init__(self, question: str, config_toml: str) -> None:
            self.question = question
            self.config_toml = config_toml
            super().__init__()

    class ContinueRequested(Message):
        """Emitted when user clicks Continue — pre-fill Ask form with prior context."""
        def __init__(self, run_id: int) -> None:
            self.run_id = run_id
            super().__init__()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "dv-open" and self._run_dir:
            from pathlib import Path
            from dissenter.paths import open_in_finder
            p = Path(self._run_dir)
            if p.exists():
                open_in_finder(p)
            else:
                self.app.notify(f"Folder not found: {p}", severity="error")
        elif event.button.id == "dv-rerun":
            self._do_rerun()
        elif event.button.id == "dv-continue":
            self.post_message(self.ContinueRequested(self._run_id))
        elif event.button.id == "dv-back":
            from textual.widgets import ContentSwitcher
            try:
                self.app.query_one("#content-switcher", ContentSwitcher).current = "content-history"
            except Exception:
                pass

    def _do_rerun(self) -> None:
        """Re-run the same debate: same question, same config."""
        from dissenter.db import get_run

        run = get_run(self._run_id)
        if not run:
            self.app.notify("Decision not found", severity="error")
            return

        # Write the config snapshot to a temp file and launch debate
        from pathlib import Path
        from dissenter.paths import configs_dir, ensure_dirs
        ensure_dirs()
        tmp_cfg = configs_dir() / "_rerun.toml"
        tmp_cfg.write_text(run["config_toml"], encoding="utf-8")

        from dissenter.tui.screens.debate import DebateScreen
        screen = DebateScreen(
            question=run["question"],
            config_path=str(tmp_cfg),
        )
        self.app.push_screen(screen, callback=self.app._on_debate_done)
