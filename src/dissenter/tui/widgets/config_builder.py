"""Config builder — visual step-by-step config creation (TUI version of `dissenter init`)."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Button, Input, Label, Select, Static


_ROLE_CHOICES = [
    ("devil's advocate", "devil's advocate"),
    ("pragmatist", "pragmatist"),
    ("skeptic", "skeptic"),
    ("contrarian", "contrarian"),
    ("analyst", "analyst"),
    ("researcher", "researcher"),
    ("second opinion", "second opinion"),
    ("chairman", "chairman"),
    ("conservative", "conservative"),
    ("liberal", "liberal"),
]

_AUTH_CHOICES = [
    ("API key (env var)", "api"),
    ("CLI (claude/gemini)", "cli"),
]


def _detect_model_choices() -> list[tuple[str, str]]:
    """Build model choices from detected environment. Lazy — only called on mount."""
    choices: list[tuple[str, str]] = []
    try:
        from dissenter.detect import detect_ollama_models, detect_clis, detect_api_keys
        from dissenter.wizard import _CLOUD_MODELS_BY_PROVIDER, _PROVIDER_CLI

        # Ollama models
        for m in detect_ollama_models():
            choices.append((f"ollama/{m}", f"ollama/{m}"))

        # Cloud models with detected credentials
        clis = detect_clis()
        api_keys = detect_api_keys()
        for provider, models in _CLOUD_MODELS_BY_PROVIDER.items():
            cli_name = _PROVIDER_CLI.get(provider)
            has_cli = cli_name and clis.get(cli_name)
            has_key = api_keys.get(provider, False)
            if has_cli or has_key:
                for model_id in models:
                    choices.append((model_id, model_id))
    except Exception:
        pass

    if not choices:
        choices.append(("— (no models detected)", ""))

    choices.append(("custom (type below)", "__custom__"))
    return choices


class ModelRow(Vertical):
    """A single model entry within a round."""

    DEFAULT_CSS = """
    ModelRow {
        height: auto;
        padding: 1 1;
        margin-bottom: 1;
        background: $surface;
    }
    ModelRow .model-row-line {
        height: auto;
    }
    ModelRow Label {
        width: 10;
        padding: 1 1 0 0;
        text-style: dim;
    }
    ModelRow Select {
        width: 1fr;
    }
    ModelRow Input {
        width: 1fr;
    }
    ModelRow .model-custom-input {
        display: none;
    }
    ModelRow .timeout-input {
        width: 12;
    }
    ModelRow .model-row-footer {
        height: auto;
    }
    ModelRow .model-row-footer Button {
        margin-right: 1;
    }
    """

    def __init__(self, model_choices: list[tuple[str, str]], role: str = "analyst", auth: str = "api") -> None:
        super().__init__()
        self._model_choices = model_choices
        self._initial_role = role
        self._initial_auth = auth

    def compose(self) -> ComposeResult:
        with Horizontal(classes="model-row-line"):
            yield Label("Model")
            yield Select(self._model_choices, prompt="select model", classes="model-select", allow_blank=False)
        yield Input(placeholder="custom model ID (e.g. openai/gpt-4o)", classes="model-custom-input")
        with Horizontal(classes="model-row-line"):
            yield Label("Role")
            yield Select(_ROLE_CHOICES, value=self._initial_role, classes="role-select", allow_blank=False)
        with Horizontal(classes="model-row-line"):
            yield Label("Auth")
            yield Select(_AUTH_CHOICES, value=self._initial_auth, classes="auth-select", allow_blank=False)
        with Horizontal(classes="model-row-line"):
            yield Label("Timeout")
            yield Input(value="180", placeholder="seconds", classes="timeout-input")
        with Horizontal(classes="model-row-footer"):
            yield Button("✕ Remove model", variant="error", classes="remove-model-btn")

    def on_select_changed(self, event: Select.Changed) -> None:
        if "model-select" in event.select.classes:
            custom_input = self.query_one(".model-custom-input", Input)
            if event.value == "__custom__":
                custom_input.styles.display = "block"
                custom_input.focus()
            else:
                custom_input.styles.display = "none"

    def get_data(self) -> dict:
        model_select = self.query_one(".model-select", Select)
        model_id = str(model_select.value) if model_select.value != "__custom__" else ""
        if model_id == "__custom__" or not model_id:
            model_id = self.query_one(".model-custom-input", Input).value.strip()
        role = str(self.query_one(".role-select", Select).value)
        auth = str(self.query_one(".auth-select", Select).value)
        try:
            timeout = int(self.query_one(".timeout-input", Input).value.strip())
        except (ValueError, AttributeError):
            timeout = 180
        return {"id": model_id, "role": role, "auth": auth, "timeout": timeout}


class RoundBlock(Vertical):
    """A single round with its models and an add-model button."""

    DEFAULT_CSS = """
    RoundBlock {
        height: auto;
        padding: 1 2;
        margin-bottom: 1;
        border: solid $primary-background;
    }
    RoundBlock .round-header {
        height: 1;
        text-style: bold;
    }
    RoundBlock .model-list {
        height: auto;
    }
    RoundBlock .round-name-input {
        margin-bottom: 1;
    }
    RoundBlock .round-btns {
        height: auto;
    }
    RoundBlock .round-btns Button {
        margin-right: 1;
    }
    """

    def __init__(self, round_num: int, name: str = "", is_final: bool = False, model_choices: list | None = None) -> None:
        super().__init__()
        self._round_num = round_num
        self._round_name = name
        self._is_final = is_final
        self._model_choices = model_choices or []

    def compose(self) -> ComposeResult:
        suffix = " [yellow](final)[/yellow]" if self._is_final else ""
        yield Static(f"Round {self._round_num}{suffix}", classes="round-header", markup=True)
        yield Input(value=self._round_name, placeholder="round name (e.g. debate, refine, final)", classes="round-name-input")
        default_role = "chairman" if self._is_final else "analyst"
        with Vertical(classes="model-list"):
            yield ModelRow(self._model_choices, role=default_role)
        with Horizontal(classes="round-btns"):
            yield Button("+ Add model", classes="add-model-btn", variant="success")
            if not self._is_final:
                yield Button("✕ Remove round", classes="remove-round-btn", variant="error")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if "add-model-btn" in event.button.classes:
            container = self.query_one(".model-list")
            default_role = "chairman" if self._is_final else "analyst"
            await container.mount(ModelRow(self._model_choices, role=default_role))
            self._update_remove_buttons()
            event.stop()
        elif "remove-model-btn" in event.button.classes:
            # Walk up the ancestor chain to find the ModelRow (button is nested in a Horizontal)
            ancestor = event.button.parent
            while ancestor is not None and not isinstance(ancestor, ModelRow):
                ancestor = ancestor.parent
            if ancestor is not None:
                await ancestor.remove()
                self._update_remove_buttons()
            event.stop()
        elif "remove-round-btn" in event.button.classes:
            await self.remove()
            event.stop()

    def _update_remove_buttons(self) -> None:
        """Disable the remove-model button when only one model remains."""
        rows = list(self.query(ModelRow))
        only_one = len(rows) == 1
        for row in rows:
            try:
                btn = row.query_one(".remove-model-btn", Button)
                btn.disabled = only_one
            except Exception:
                pass

    def on_mount(self) -> None:
        self._update_remove_buttons()

    def get_data(self) -> dict:
        name = self.query_one(".round-name-input", Input).value.strip()
        models = [row.get_data() for row in self.query(ModelRow)]
        return {"name": name or f"round_{self._round_num}", "models": models}


class ConfigBuilder(VerticalScroll):
    """Visual config builder — add rounds, add models per round, set roles and auth."""

    class ConfigReady(Message):
        """Emitted when the user clicks Save with valid config data."""
        def __init__(self, rounds_data: list[dict], output_name: str) -> None:
            self.rounds_data = rounds_data
            self.output_name = output_name
            super().__init__()

    DEFAULT_CSS = """
    ConfigBuilder {
        padding: 2 4;
    }
    ConfigBuilder .builder-title {
        text-style: bold;
        margin-bottom: 1;
    }
    ConfigBuilder .builder-desc {
        color: $text-muted;
        margin-bottom: 1;
    }
    ConfigBuilder #builder-rounds {
        height: auto;
    }
    ConfigBuilder #builder-actions {
        height: auto;
        margin-top: 1;
        padding: 1 0;
    }
    ConfigBuilder #builder-actions Button {
        margin-right: 1;
    }
    ConfigBuilder #builder-error {
        color: $error;
        display: none;
        margin-top: 1;
    }
    ConfigBuilder .config-name-row {
        height: auto;
        margin-bottom: 1;
    }
    ConfigBuilder .config-name-row Input {
        width: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        self._round_counter = 2
        self._model_choices = _detect_model_choices()
        yield Static("Create a debate config", classes="builder-title")
        yield Static(
            "Add rounds with models and roles. The last round is always the final (chairman or dual arbiter).",
            classes="builder-desc",
        )
        with Horizontal(classes="config-name-row"):
            yield Label("Config name: ")
            yield Input(placeholder="leave blank for timestamp", id="config-name-input")
        with Vertical(id="builder-rounds"):
            yield RoundBlock(1, "debate", is_final=False, model_choices=self._model_choices)
            yield RoundBlock(2, "final", is_final=True, model_choices=self._model_choices)
        with Horizontal(id="builder-actions"):
            yield Button("+ Add debate round", id="add-round-btn", variant="default")
            yield Button("Save config", id="save-config-btn", variant="primary")
            yield Button("Reset", id="reset-config-btn", variant="error")
        yield Static("", id="builder-error")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add-round-btn":
            await self._add_round()
            event.stop()
        elif event.button.id == "save-config-btn":
            self._save()
        elif event.button.id == "reset-config-btn":
            await self._reset()

    async def _reset(self) -> None:
        """Clear the builder back to the default 2-round template."""
        container = self.query_one("#builder-rounds")
        for block in list(container.query(RoundBlock)):
            await block.remove()

        self.query_one("#config-name-input", Input).value = ""

        await container.mount(RoundBlock(1, "debate", is_final=False, model_choices=self._model_choices))
        await container.mount(RoundBlock(2, "final", is_final=True, model_choices=self._model_choices))
        self._round_counter = 2

        error_label = self.query_one("#builder-error", Static)
        error_label.styles.display = "none"

        self.app.notify("Config builder reset", title="Reset")

    async def _add_round(self) -> None:
        """Insert a new debate round between the last debate round and the final.

        Snapshots all current round data, rebuilds the container with the new
        round inserted at the correct position, then restores everything. This
        guarantees ordering and preserves all user input across all rounds.
        """
        container = self.query_one("#builder-rounds")
        blocks = list(container.query(RoundBlock))

        if not blocks:
            # No rounds — create a fresh debate + final pair
            await container.mount(RoundBlock(1, "round_1", is_final=False, model_choices=self._model_choices))
            await container.mount(RoundBlock(2, "final", is_final=True, model_choices=self._model_choices))
            self._round_counter = 2
            return

        # Snapshot all rounds
        snapshots = [b.get_data() for b in blocks]
        is_finals = [b._is_final for b in blocks]

        # Insert a new debate-round snapshot just before the final
        debate_count = sum(1 for f in is_finals if not f)
        new_snapshot = {"name": f"round_{debate_count + 1}", "models": []}
        # Insert before the last (final) entry
        snapshots.insert(-1, new_snapshot)
        is_finals.insert(-1, False)

        # Wipe and rebuild
        for b in blocks:
            await b.remove()

        for i, (snap, is_final) in enumerate(zip(snapshots, is_finals), 1):
            block = RoundBlock(
                i, snap["name"], is_final=is_final, model_choices=self._model_choices,
            )
            await container.mount(block)

            # Restore models for this round (replace the default model row)
            if snap["models"]:
                model_list = block.query_one(".model-list")
                for default_row in list(model_list.query(ModelRow)):
                    await default_row.remove()

                known_ids = {v for _, v in self._model_choices if v != "__custom__"}
                for m in snap["models"]:
                    role = m.get("role", "chairman" if is_final else "analyst")
                    auth = m.get("auth", "api")
                    row = ModelRow(self._model_choices, role=role, auth=auth)
                    await model_list.mount(row)

                    model_id = m.get("id", "")
                    model_select = row.query_one(".model-select", Select)
                    if model_id and model_id in known_ids:
                        model_select.value = model_id
                    elif model_id:
                        model_select.value = "__custom__"
                        custom_input = row.query_one(".model-custom-input", Input)
                        custom_input.value = model_id
                        custom_input.styles.display = "block"

                    timeout = m.get("timeout", 180)
                    row.query_one(".timeout-input", Input).value = str(timeout)

            block._update_remove_buttons()

        self._round_counter = len(snapshots)
        self._renumber()

    def _renumber(self) -> None:
        """Renumber all round headers sequentially."""
        container = self.query_one("#builder-rounds")
        blocks = list(container.query(RoundBlock))
        for i, block in enumerate(blocks, 1):
            block._round_num = i
            suffix = " [yellow](final)[/yellow]" if block._is_final else ""
            try:
                header = block.query_one(".round-header", Static)
                header.update(f"Round {i}{suffix}")
            except Exception:
                pass

    async def load_from_config(self, path: "Path") -> None:
        """Parse a TOML config and rebuild the builder UI from it."""
        import tomllib
        from pathlib import Path as _P

        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            self.app.notify(f"Failed to parse: {e}", severity="error")
            return

        rounds = data.get("rounds", [])
        if not rounds:
            self.app.notify("Config has no rounds", severity="warning")
            return

        # Set the config name from filename (strip dissenter_ prefix and .toml suffix)
        name_input = self.query_one("#config-name-input", Input)
        stem = path.stem
        if stem.startswith("dissenter_"):
            stem = stem[len("dissenter_"):]
        name_input.value = stem

        # Clear existing round blocks
        container = self.query_one("#builder-rounds")
        for block in list(container.query(RoundBlock)):
            await block.remove()

        # Rebuild rounds from parsed data
        if not self._model_choices:
            self._model_choices = _detect_model_choices()

        for i, rnd in enumerate(rounds):
            is_final = i == len(rounds) - 1
            name = rnd.get("name", f"round_{i + 1}")
            block = RoundBlock(
                i + 1, name, is_final=is_final, model_choices=self._model_choices,
            )
            await container.mount(block)

            # Replace the default model row with the actual models from config
            models = rnd.get("models", [])
            if models:
                model_list = block.query_one(".model-list")
                # Remove the default ModelRow that compose() created
                for default_row in list(model_list.query(ModelRow)):
                    await default_row.remove()

                for m in models:
                    role = m.get("role", "chairman" if is_final else "analyst")
                    auth = m.get("auth", "api")
                    row = ModelRow(self._model_choices, role=role, auth=auth)
                    await model_list.mount(row)

                    # Set the model select (or custom input if not in choices)
                    model_id = m.get("id", "")
                    known_ids = {v for _, v in self._model_choices if v != "__custom__"}
                    model_select = row.query_one(".model-select", Select)
                    if model_id in known_ids:
                        model_select.value = model_id
                    else:
                        model_select.value = "__custom__"
                        custom_input = row.query_one(".model-custom-input", Input)
                        custom_input.value = model_id
                        custom_input.styles.display = "block"

                    # Set timeout
                    timeout = m.get("timeout", 180)
                    row.query_one(".timeout-input", Input).value = str(timeout)

            block._update_remove_buttons()

        self._round_counter = len(rounds)

    def _save(self) -> None:
        error_label = self.query_one("#builder-error", Static)
        rounds_data = [block.get_data() for block in self.query(RoundBlock)]

        # Validate
        if len(rounds_data) < 2:
            error_label.update("Need at least 2 rounds (debate + final).")
            error_label.styles.display = "block"
            return

        for i, rd in enumerate(rounds_data):
            if not rd["models"]:
                error_label.update(f"Round {i+1} has no models.")
                error_label.styles.display = "block"
                return
            for m in rd["models"]:
                if not m["id"]:
                    error_label.update(f"Round {i+1} has a model with no ID.")
                    error_label.styles.display = "block"
                    return

        error_label.styles.display = "none"

        name = self.query_one("#config-name-input", Input).value.strip()
        self.post_message(self.ConfigReady(rounds_data=rounds_data, output_name=name))
