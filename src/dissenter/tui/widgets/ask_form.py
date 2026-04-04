from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, Input, Label, Select, Switch


class AskForm(Vertical):
    """Form to configure and start a new debate."""

    class DebateRequested(Message):
        """Emitted when the user clicks Start Debate with a valid question."""

        def __init__(
            self,
            question: str,
            config_path: str | None,
            context_paths: list[str],
            prior_id: int | None,
            deep: bool,
        ) -> None:
            self.question = question
            self.config_path = config_path
            self.context_paths = context_paths
            self.prior_id = prior_id
            self.deep = deep
            super().__init__()

    DEFAULT_CSS = """
    AskForm {
        padding: 2 4;
        height: auto;
    }
    AskForm Label {
        margin-top: 1;
        text-style: bold;
    }
    AskForm Input {
        margin-bottom: 0;
    }
    AskForm Select {
        margin-bottom: 0;
    }
    AskForm #deep-row {
        height: auto;
        margin-top: 1;
        margin-bottom: 1;
    }
    AskForm #deep-row Label {
        margin-top: 0;
        margin-left: 1;
    }
    AskForm #start-btn {
        margin-top: 1;
        width: auto;
    }
    AskForm #validation-error {
        color: $error;
        margin-top: 1;
        display: none;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("What's the question?")
        yield Input(
            id="question-input",
            placeholder="Should we use Kafka or Postgres outbox?",
        )
        yield Label("Config")
        yield Select(
            options=[("dissenter.toml (default)", None)],
            id="config-select",
            value=None,
            allow_blank=False,
        )
        yield Label("Context files (optional)")
        yield Input(
            id="context-input",
            placeholder="path/to/file.md, another.md",
        )
        yield Label("Prior decision ID (optional)")
        yield Input(
            id="prior-input",
            placeholder="e.g. 3",
        )
        with Horizontal(id="deep-row"):
            yield Switch(id="deep-switch", value=False)
            yield Label("Enable mutual critique (--deep)")
        yield Label("", id="validation-error")
        yield Button("Start Debate", id="start-btn", variant="primary")

    def on_mount(self) -> None:
        """Populate the config Select with detected config files and presets."""
        from dissenter.paths import configs_dir

        options: list[tuple[str, str | None]] = [
            ("dissenter.toml (default)", None),
        ]

        # Check for dissenter*.toml in cwd
        cwd = Path.cwd()
        for p in sorted(cwd.glob("dissenter_*.toml")):
            options.append((p.name, str(p)))

        # Check saved configs in ~/Documents/dissenter/configs/
        cfg_dir = configs_dir()
        if cfg_dir.is_dir():
            for p in sorted(cfg_dir.glob("*.toml")):
                if p.name.startswith("_"):
                    continue  # skip internal files like _rerun.toml
                label = p.name
                # Don't duplicate if already found in cwd
                if str(p) not in [o[1] for o in options]:
                    options.append((label, str(p)))

        # Add the quick/auto-detect option
        options.append(("Quick (auto-detect Ollama)", "__quick__"))

        select = self.query_one("#config-select", Select)
        select.set_options(options)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "start-btn":
            return

        question_input = self.query_one("#question-input", Input)
        question = question_input.value.strip()

        error_label = self.query_one("#validation-error", Label)

        if not question:
            error_label.update("Question cannot be empty.")
            error_label.styles.display = "block"
            question_input.focus()
            return

        error_label.styles.display = "none"

        # Gather config path
        config_select = self.query_one("#config-select", Select)
        config_val = config_select.value
        config_path: str | None = None
        if config_val == "__quick__":
            from dissenter.detect import detect_ollama_models
            if not detect_ollama_models():
                self.app.notify(
                    "Quick mode requires local Ollama models.\n"
                    "Install Ollama and run: ollama pull mistral",
                    severity="error",
                    title="No Ollama models detected",
                )
                return
            config_path = "__quick__"
        elif config_val is not None:
            config_path = str(config_val)

        # Gather context paths
        context_raw = self.query_one("#context-input", Input).value.strip()
        context_paths = [p.strip() for p in context_raw.split(",") if p.strip()] if context_raw else []

        # Gather prior ID
        prior_raw = self.query_one("#prior-input", Input).value.strip()
        prior_id: int | None = None
        if prior_raw:
            try:
                prior_id = int(prior_raw)
            except ValueError:
                error_label.update("Prior decision ID must be a number.")
                error_label.styles.display = "block"
                return

        deep = self.query_one("#deep-switch", Switch).value

        self.post_message(
            self.DebateRequested(
                question=question,
                config_path=config_path,
                context_paths=context_paths,
                prior_id=prior_id,
                deep=deep,
            )
        )

    def set_prior(self, run_id: int) -> None:
        """Pre-fill the prior decision ID and focus the question input."""
        try:
            self.query_one("#prior-input", Input).value = str(run_id)
            self.query_one("#question-input", Input).focus()
        except Exception:
            pass
