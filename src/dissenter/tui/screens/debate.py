from __future__ import annotations

import random
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, LoadingIndicator, MarkdownViewer, RichLog, Static
from textual.worker import Worker


class DebateScreen(Screen):
    """Full-screen view showing live debate progress."""

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
    ]

    DEFAULT_CSS = """
    DebateScreen {
        background: $surface;
    }
    DebateScreen #debate-header {
        padding: 1 2;
        text-style: bold;
        color: $text;
        background: $primary-background;
    }
    DebateScreen #debate-question {
        padding: 0 2 1 2;
        color: $text-muted;
        text-style: italic;
    }
    DebateScreen #loading-area {
        height: auto;
        padding: 2 4;
        align: center middle;
    }
    DebateScreen #loading-message {
        text-align: center;
        color: $text-muted;
        text-style: italic;
        padding: 1 0;
    }
    DebateScreen #loading-indicator {
        height: 3;
    }
    DebateScreen #progress-log {
        height: auto;
        max-height: 20;
        padding: 0 2;
        margin-top: 1;
    }
    DebateScreen #error-message {
        padding: 2 4;
        color: $error;
        display: none;
    }
    DebateScreen #result-viewer {
        display: none;
    }
    """

    def __init__(
        self,
        question: str,
        config_path: str | None = None,
        context_paths: list[str] | None = None,
        prior_id: int | None = None,
        deep: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._question = question
        self._config_path = config_path
        self._context_paths = context_paths or []
        self._prior_id = prior_id
        self._deep = deep
        self._message_index = 0
        self._cancelled = False
        self._debate_loop = None  # asyncio loop used by worker thread

    def compose(self) -> ComposeResult:
        yield Static("Debate in progress...", id="debate-header")
        yield Static(self._question, id="debate-question")
        with VerticalScroll():
            with Vertical(id="loading-area"):
                yield LoadingIndicator(id="loading-indicator")
                yield Static(self._random_loading_message(), id="loading-message")
                yield RichLog(id="progress-log", markup=True, highlight=True)
            yield Static("", id="error-message")
            yield MarkdownViewer(id="result-viewer", show_table_of_contents=False)
        yield Footer()

    def on_mount(self) -> None:
        """Run pre-flight checks, then start the debate."""
        self._rotate_timer = self.set_interval(4.0, self._rotate_message)

        # Pre-flight: validate all models are available before starting
        preflight_errors = self._run_preflight()
        if preflight_errors:
            self._show_error(
                "Pre-flight check failed:\n\n"
                + "\n".join(f"  • {e.message}" for e in preflight_errors)
            )
            return

        self._run_debate_worker()

    def _run_preflight(self) -> list:
        """Validate config models are available. Returns list of errors (empty = OK)."""
        from dissenter.config import load_config, config_to_toml
        from dissenter.detect import detect_ollama_models, detect_clis, detect_api_keys
        from dissenter.validate import validate_toml

        try:
            if self._config_path == "__quick__":
                from dissenter.cli import _config_from_quick
                cfg = _config_from_quick(output_dir=None)
            else:
                from pathlib import Path
                cfg = load_config(Path(self._config_path) if self._config_path else None)

            _, errors = validate_toml(
                config_to_toml(cfg),
                detect_ollama_models(), detect_clis(), detect_api_keys(),
            )
            return [e for e in errors if e.stage == "preflight"]
        except Exception as exc:
            from dissenter.validate import ConfigError
            return [ConfigError("preflight", str(exc))]

    def _random_loading_message(self) -> str:
        from dissenter.wizard import _LOADING_MESSAGES

        return random.choice(_LOADING_MESSAGES)

    def _random_synthesis_message(self) -> str:
        from dissenter.wizard import _SYNTHESIS_MESSAGES

        return random.choice(_SYNTHESIS_MESSAGES)

    def _rotate_message(self) -> None:
        """Rotate through loading/synthesis messages."""
        from dissenter.wizard import _LOADING_MESSAGES, _SYNTHESIS_MESSAGES

        all_messages = _LOADING_MESSAGES + _SYNTHESIS_MESSAGES
        self._message_index = (self._message_index + 1) % len(all_messages)
        try:
            label = self.query_one("#loading-message", Static)
            label.update(all_messages[self._message_index])
        except Exception:
            pass

    @staticmethod
    def _load_user_context(paths: list[str]) -> str:
        """Read context files and concatenate their contents."""
        from pathlib import Path

        parts: list[str] = []
        for p in paths:
            fp = Path(p)
            if fp.is_file():
                parts.append(f"--- {fp.name} ---\n{fp.read_text(encoding='utf-8')}")
        return "\n\n".join(parts)

    def _run_debate_worker(self) -> None:
        """Launch the debate in a thread worker."""
        self.run_worker(
            self._debate_thread,
            thread=True,
            exclusive=True,
            name="debate-worker",
        )

    def _log_progress(self, event: str, data: dict) -> None:
        """Called from the debate thread — posts updates to the TUI progress log."""
        try:
            app = self.app
        except Exception:
            return  # screen already dismissed

        if event == "round_start":
            msg = f"[bold]── Round {data['round_num']} of {data['total']}: {data['name']} ({data['n_models']} models) ──[/bold]"
            app.call_from_thread(self._append_log, msg)
        elif event == "model_start":
            msg = f"  [yellow]●[/yellow] {data['model_id']} [dim]({data['role']})[/dim] — running..."
            app.call_from_thread(self._append_log, msg)
        elif event == "model_done":
            if data["success"]:
                conf = f" · confidence {data['confidence']}/10" if data.get("confidence") else ""
                msg = f"  [green]✓[/green] {data['model_id']} [dim]({data['role']})[/dim] — {data['elapsed']:.0f}s · ~{data['word_count']} words{conf}"
            else:
                msg = f"  [red]✗[/red] {data['model_id']} [dim]({data['role']})[/dim] — {data.get('error', 'failed')}"
            app.call_from_thread(self._append_log, msg)

    def _append_log(self, text: str) -> None:
        try:
            log = self.query_one("#progress-log", RichLog)
            log.write(text)
        except Exception:
            pass

    def _debate_thread(self) -> None:
        """Run the full debate pipeline in a background thread."""
        import asyncio

        from dissenter.config import load_config
        from dissenter.runner import run_all_rounds
        from dissenter.synthesis import synthesize

        # Create a persistent loop for this thread so we can cancel its tasks
        loop = asyncio.new_event_loop()
        self._debate_loop = loop

        try:
            # Load config
            if self._config_path == "__quick__":
                from dissenter.cli import _config_from_quick

                cfg = _config_from_quick(output_dir=None)
            else:
                from pathlib import Path

                cfg = load_config(Path(self._config_path) if self._config_path else None)

            if self._cancelled:
                return

            # Build user context from files
            user_context = self._load_user_context(self._context_paths)

            # Run all debate rounds with progress callback
            all_rounds = loop.run_until_complete(
                run_all_rounds(
                    cfg, self._question, deep=self._deep,
                    user_context=user_context, on_progress=self._log_progress,
                )
            )

            if self._cancelled:
                return

            # Synthesize ADR
            try:
                self.app.call_from_thread(self._append_log, "\n[bold]── Synthesizing decision ──[/bold]")
                self.app.call_from_thread(self._show_synthesizing)
            except Exception:
                pass
            final_text, results = loop.run_until_complete(
                synthesize(self._question, all_rounds, cfg)
            )

            if self._cancelled:
                return

            # Generate a single-word name for the decision
            import random
            from dissenter.synthesis import name_decision
            naming_model = random.choice(cfg.rounds[-1].active_models)
            decision_name = loop.run_until_complete(
                name_decision(self._question, final_text, naming_model)
            )

            # Save outputs
            from datetime import datetime
            from dissenter.paths import ensure_dirs
            from dissenter.config import config_to_toml
            ensure_dirs()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            folder_name = f"{ts}_{decision_name}" if decision_name else ts
            run_dir = cfg.output_dir / folder_name
            run_dir.mkdir(parents=True, exist_ok=True)

            for rr in all_rounds:
                round_dir = run_dir / f"round_{rr.round_index + 1}_{rr.round_name}"
                round_dir.mkdir(exist_ok=True)
                for r in rr.results:
                    safe = r.model_id.replace("/", "_").replace(":", "_")
                    role_safe = r.role.replace(" ", "_").replace("'", "")
                    (round_dir / f"{safe}__{role_safe}.md").write_text(r.content or "", encoding="utf-8")

            output_file = run_dir / "decision.md"
            output_file.write_text(final_text, encoding="utf-8")
            cfg_toml = config_to_toml(cfg)
            (run_dir / "config.toml").write_text(cfg_toml, encoding="utf-8")

            # Persist to DB
            from dissenter.db import save_run
            try:
                save_run(
                    question=self._question, config_toml=cfg_toml,
                    decision_md=final_text, run_dir=str(run_dir.absolute()),
                    rounds=[{"round_index": rr.round_index, "name": rr.round_name,
                             "outputs": [{"model_id": r.model_id, "role": r.role, "auth": "api",
                                          "content_md": r.content, "error_msg": r.error, "elapsed_ms": None}
                                         for r in rr.results]}
                            for rr in all_rounds],
                )
            except Exception:
                pass

            # Show result
            if not self._cancelled:
                try:
                    self.app.call_from_thread(self._show_result, final_text)
                except Exception:
                    pass

        except asyncio.CancelledError:
            pass  # expected when user navigates back
        except Exception as exc:
            if not self._cancelled:
                try:
                    self.app.call_from_thread(self._show_error, str(exc))
                except Exception:
                    pass
        finally:
            loop.close()
            self._debate_loop = None

    def _show_synthesizing(self) -> None:
        """Update the loading message to indicate synthesis phase."""
        try:
            label = self.query_one("#loading-message", Static)
            label.update(self._random_synthesis_message())
        except Exception:
            pass

    def _show_result(self, final_text: str) -> None:
        """Replace loading UI with the final ADR in a MarkdownViewer."""
        self._rotate_timer.stop()

        try:
            header = self.query_one("#debate-header", Static)
            header.update("Debate complete")
        except Exception:
            pass

        try:
            loading_area = self.query_one("#loading-area", Vertical)
            loading_area.styles.display = "none"
        except Exception:
            pass

        try:
            viewer = self.query_one("#result-viewer", MarkdownViewer)
            viewer.styles.display = "block"
            viewer.document.update(final_text)
        except Exception:
            pass

    def _show_error(self, error_msg: str) -> None:
        """Show an error message if the debate fails."""
        self._rotate_timer.stop()

        try:
            header = self.query_one("#debate-header", Static)
            header.update("Debate failed")
        except Exception:
            pass

        try:
            loading_area = self.query_one("#loading-area", Vertical)
            loading_area.styles.display = "none"
        except Exception:
            pass

        try:
            error_label = self.query_one("#error-message", Static)
            error_label.update(f"Error: {error_msg}")
            error_label.styles.display = "block"
        except Exception:
            pass

    def action_go_back(self) -> None:
        """Return to the main app screen — cancel any running debate."""
        self._cancelled = True
        # Cancel all tasks on the worker's asyncio loop if it's still running
        if self._debate_loop and self._debate_loop.is_running():
            for task in __import__("asyncio").all_tasks(self._debate_loop):
                self._debate_loop.call_soon_threadsafe(task.cancel)
        # Cancel textual workers
        for worker in self.workers:
            worker.cancel()
        self.dismiss(True)
