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

    def compose(self) -> ComposeResult:
        yield Label(
            "[dim]An LLM will read your description, your detected models/keys,[/dim]\n"
            "[dim]and the full role catalog — then write a valid debate config for you.[/dim]",
            markup=True,
        )
        yield Label("Describe the config you want")
        yield Input(
            id="gen-prompt",
            placeholder="fast 2-round debate with local ollama models",
        )
        yield Label("Generator model (optional)")
        yield Input(
            id="gen-model",
            placeholder="auto-detect",
        )
        yield Label("Output name (optional)")
        yield Input(
            id="gen-output",
            placeholder="timestamped if blank",
        )
        yield Label("", id="gen-validation-error")
        yield Button("Generate", id="gen-btn", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "gen-btn":
            return

        prompt_input = self.query_one("#gen-prompt", Input)
        prompt = prompt_input.value.strip()

        error_label = self.query_one("#gen-validation-error", Label)

        if not prompt:
            error_label.update("Prompt cannot be empty.")
            error_label.styles.display = "block"
            prompt_input.focus()
            return

        error_label.styles.display = "none"

        model_raw = self.query_one("#gen-model", Input).value.strip()
        model = model_raw if model_raw else None

        output_raw = self.query_one("#gen-output", Input).value.strip()
        output_name = output_raw if output_raw else None

        self.post_message(
            self.GenerateRequested(
                prompt=prompt,
                model=model,
                output_name=output_name,
            )
        )
