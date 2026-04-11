"""Benchmark form — configure and start a benchmark run from the TUI.

Mirrors the CLI `dissenter benchmark` surface: dataset picker, config
picker, limit, output filename, mode selector (dissenter / single /
majority / competitor), and a Start button.
"""
from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, Input, Label, Select


class BenchmarkForm(Vertical):
    """Form to configure and start a benchmark run."""

    class BenchmarkRequested(Message):
        """User clicked Start — carries all form state."""

        def __init__(
            self,
            dataset_path: str,
            config_path: str | None,
            output_path: str,
            limit: int,
            mode: str,
            majority_n: int,
            deep: bool,
            competitor: str | None,
        ) -> None:
            self.dataset_path = dataset_path
            self.config_path = config_path
            self.output_path = output_path
            self.limit = limit
            self.mode = mode
            self.majority_n = majority_n
            self.deep = deep
            self.competitor = competitor
            super().__init__()

    DEFAULT_CSS = """
    BenchmarkForm {
        padding: 2 4;
        height: auto;
    }
    BenchmarkForm Label {
        margin-top: 1;
        text-style: bold;
    }
    BenchmarkForm Input, BenchmarkForm Select {
        margin-bottom: 0;
    }
    BenchmarkForm #bm-validation-error {
        color: $error;
        margin-top: 1;
        display: none;
    }
    BenchmarkForm #bm-start {
        margin-top: 1;
        width: auto;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("Dataset")
        yield Select(
            options=[("(none found)", None)],
            id="bm-dataset",
            allow_blank=False,
        )

        yield Label("Config")
        yield Select(
            options=[("dissenter.toml (default)", None)],
            id="bm-config",
            allow_blank=False,
        )

        yield Label("Mode")
        yield Select(
            options=[
                ("dissenter (full debate)", "dissenter"),
                ("dissenter + --deep critique", "dissenter-deep"),
                ("single model (no debate)", "single"),
                ("majority vote (same model × N)", "majority"),
                ("llm-council (competitor)", "llm-council"),
                ("llm-consortium (competitor)", "llm-consortium"),
                ("consilium (competitor)", "consilium"),
            ],
            value="dissenter",
            id="bm-mode",
            allow_blank=False,
        )

        yield Label("Question limit (0 = all)")
        yield Input(id="bm-limit", value="0")

        yield Label("Majority N (for majority mode)")
        yield Input(id="bm-majority-n", value="3")

        yield Label("Output filename")
        yield Input(id="bm-output", placeholder="results/run.json")

        yield Label("", id="bm-validation-error")
        yield Button("Start benchmark", id="bm-start", variant="primary")

    def on_mount(self) -> None:
        self.refresh_options()

    def refresh_options(self) -> None:
        """Re-scan datasets/ and configs dirs to populate the dropdowns."""
        self._populate_datasets()
        self._populate_configs()

    def _populate_datasets(self) -> None:
        options: list[tuple[str, str]] = []
        dataset_dir = Path.cwd() / "datasets"
        if dataset_dir.is_dir():
            for p in sorted(dataset_dir.glob("*.jsonl")):
                options.append((p.name, str(p)))
        if not options:
            options = [("(no .jsonl files in ./datasets)", "")]
        try:
            sel = self.query_one("#bm-dataset", Select)
            current = sel.value
            sel.set_options(options)
            if current and any(o[1] == current for o in options):
                sel.value = current
        except Exception:
            pass

    def _populate_configs(self) -> None:
        from dissenter.paths import configs_dir

        options: list[tuple[str, str | None]] = [
            ("dissenter.toml (default)", None),
        ]

        # Pinned benchmark configs (committed under configs/)
        pinned_dir = Path.cwd() / "configs"
        if pinned_dir.is_dir():
            for p in sorted(pinned_dir.glob("bench-*.toml")):
                options.append((f"[pinned] {p.name}", str(p)))

        # cwd dissenter_*.toml
        for p in sorted(Path.cwd().glob("dissenter_*.toml")):
            options.append((p.name, str(p)))

        # ~/Documents/dissenter/configs/
        cfg_dir = configs_dir()
        if cfg_dir.is_dir():
            for p in sorted(cfg_dir.glob("*.toml")):
                if p.name.startswith("_"):
                    continue
                if str(p) not in [o[1] for o in options]:
                    options.append((p.name, str(p)))

        try:
            sel = self.query_one("#bm-config", Select)
            current = sel.value
            sel.set_options(options)
            if current is not None and any(o[1] == current for o in options):
                sel.value = current
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "bm-start":
            return

        error_label = self.query_one("#bm-validation-error", Label)

        dataset_val = self.query_one("#bm-dataset", Select).value
        if not dataset_val:
            error_label.update("Pick a dataset first.")
            error_label.styles.display = "block"
            return

        config_val = self.query_one("#bm-config", Select).value
        config_path = str(config_val) if config_val is not None else None

        mode_val = str(self.query_one("#bm-mode", Select).value)
        deep = False
        competitor: str | None = None
        if mode_val == "dissenter-deep":
            mode = "dissenter"
            deep = True
        elif mode_val in ("llm-council", "llm-consortium", "consilium"):
            mode = "competitor"
            competitor = mode_val
        else:
            mode = mode_val

        try:
            limit = int(self.query_one("#bm-limit", Input).value.strip() or "0")
        except ValueError:
            error_label.update("Limit must be a number.")
            error_label.styles.display = "block"
            return

        try:
            majority_n = int(self.query_one("#bm-majority-n", Input).value.strip() or "3")
        except ValueError:
            error_label.update("Majority N must be a number.")
            error_label.styles.display = "block"
            return

        output_raw = self.query_one("#bm-output", Input).value.strip()
        if not output_raw:
            # Default: results/<dataset-stem>-<mode>.json
            stem = Path(str(dataset_val)).stem
            tag = "deep" if deep else (competitor or mode)
            output_raw = f"results/{stem}-{tag}.json"

        error_label.styles.display = "none"

        self.post_message(
            self.BenchmarkRequested(
                dataset_path=str(dataset_val),
                config_path=config_path,
                output_path=output_raw,
                limit=limit,
                mode=mode,
                majority_n=majority_n,
                deep=deep,
                competitor=competitor,
            )
        )
