from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Button, Input, Label


class GenerateForm(Vertical):
    """Form to generate a config from natural language."""

    class GenerateRequested(Message):
        """Emitted when the user clicks Generate with a valid prompt."""

        def __init__(
            self,
            prompt: str,
            model: str | None,
            output_name: str | None,
        ) -> None:
            self.prompt = prompt
            self.model = model
            self.output_name = output_name
            super().__init__()

    DEFAULT_CSS = """
    GenerateForm {
        padding: 2 4;
        height: auto;
    }
    GenerateForm Label {
        margin-top: 1;
        text-style: bold;
    }
    GenerateForm Input {
        margin-bottom: 0;
    }
    GenerateForm #gen-btn {
        margin-top: 1;
        width: auto;
    }
    GenerateForm #gen-validation-error {
        color: $error;
        margin-top: 1;
        display: none;
    }
    """

    # TODO: AI config generation is not wired up yet.
    # Needs: pick a generator model, call it with the prompt + detected env,
    # parse the TOML response, validate, and save. For now this page is disabled.

    def compose(self) -> ComposeResult:
        yield Label(
            "[bold yellow]Under construction[/bold yellow]\n\n"
            "[dim]AI-generated configs are not available yet.\n"
            "Use [bold]Create config[/bold] to build one manually, or\n"
            "use [bold]Use as template[/bold] from Saved configs to start from an existing one.[/dim]",
            markup=True,
        )
