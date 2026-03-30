from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import ContentSwitcher, Footer, Header, Static

from .widgets.sidebar import Sidebar
from .widgets.ask_form import AskForm
from .widgets.config_builder import ConfigBuilder
from .widgets.configs_list import ConfigsList
from .widgets.generate_form import GenerateForm
from .widgets.history_table import HistoryTable
from .widgets.decision_viewer import DecisionViewer
from .widgets.models_panel import ModelsPanel
from .widgets.config_tree import ConfigTree


class DissenterApp(App):
    """Dissenter TUI — structured multi-LLM debate tool."""

    TITLE = "dissenter"
    CSS_PATH = "app.tcss"

    BINDINGS = [
        Binding("n", "switch('content-ask')", "Ask", show=True),
        Binding("g", "switch('content-generate')", "Generate", show=True),
        Binding("h", "switch('content-history')", "History", show=True),
        Binding("q", "quit", "Quit", show=True),
        Binding("question_mark", "toggle_help", "Help", show=True, key_display="?"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-layout"):
            yield Sidebar(id="sidebar")
            with ContentSwitcher(id="content-switcher", initial="content-home"):
                yield VerticalScroll(self._build_home(), id="content-home")
                yield VerticalScroll(AskForm(id="ask-form"), id="content-ask")
                yield VerticalScroll(ConfigBuilder(id="config-builder"), id="content-create-config")
                yield VerticalScroll(GenerateForm(id="generate-form"), id="content-generate")
                yield VerticalScroll(HistoryTable(id="history-table"), id="content-history")
                yield VerticalScroll(DecisionViewer(id="decision-viewer"), id="content-decision")
                yield VerticalScroll(ModelsPanel(id="models-panel"), id="content-models")
                yield VerticalScroll(ConfigTree("dissenter", id="config-tree"), id="content-config")
                yield VerticalScroll(ConfigsList(id="configs-list"), id="content-configs-list")
        yield Footer()

    def _build_home(self) -> Static:
        """Build the welcome screen content with quick stats."""
        # Lazy imports to keep startup fast
        from dissenter.db import list_runs
        from dissenter.detect import detect_api_keys, detect_ollama_models
        from dissenter.paths import dissenter_home, decisions_dir, configs_dir, db_path

        try:
            runs = list_runs(limit=1000)
            num_runs = len(runs)
        except Exception:
            num_runs = 0

        try:
            api_keys = detect_api_keys()
            num_api = sum(1 for v in api_keys.values() if v)
        except Exception:
            num_api = 0

        try:
            ollama = detect_ollama_models()
            num_ollama = len(ollama)
        except Exception:
            num_ollama = 0

        num_models = num_api + num_ollama

        lines = [
            "",
            "  [bold]Welcome to dissenter[/bold]",
            "  Run multiple LLMs through structured debate.",
            "  Surface where they disagree. Synthesize a decision.",
            "",
            f"  Past decisions:   {num_runs}",
            f"  Available models: {num_models} ({num_api} API + {num_ollama} Ollama)",
            "",
            "  [dim]─── Storage ───[/dim]",
            f"  [dim]Home:      {dissenter_home()}[/dim]",
            f"  [dim]Decisions: {decisions_dir()}[/dim]",
            f"  [dim]Configs:   {configs_dir()}[/dim]",
            f"  [dim]Database:  {db_path()}[/dim]",
            "  [dim]Set DISSENTER_HOME to change the base path.[/dim]",
            "",
            "  Press [bold]n[/bold] to ask a question",
            "  Press [bold]g[/bold] to generate a config",
            "  Press [bold]?[/bold] for help",
            "",
        ]
        return Static("\n".join(lines), id="home-content", markup=True)

    def on_mount(self) -> None:
        """Load data into widgets that need it on startup."""
        try:
            self.query_one("#history-table", HistoryTable).load_runs()
        except Exception:
            pass
        try:
            self.query_one("#config-tree", ConfigTree).load_config()
        except Exception:
            pass

    def on_sidebar_selected(self, event: Sidebar.Selected) -> None:
        """Handle sidebar navigation."""
        switcher = self.query_one("#content-switcher", ContentSwitcher)

        if event.item_type == "decision" and event.data:
            viewer = self.query_one("#decision-viewer", DecisionViewer)
            run_id = event.data.get("run_id") if isinstance(event.data, dict) else event.data
            viewer.load_decision(run_id)
            switcher.current = "content-decision"
        elif event.item_type == "history":
            self.query_one("#history-table", HistoryTable).load_runs()
            switcher.current = "content-history"
        elif event.item_type == "models":
            switcher.current = "content-models"
        elif event.item_type == "config":
            self.query_one("#config-tree", ConfigTree).load_config()
            switcher.current = "content-config"
        else:
            content_id = {
                "home": "content-home",
                "ask": "content-ask",
                "generate": "content-generate",
                "create-config": "content-create-config",
                "configs-list": "content-configs-list",
            }.get(event.item_type, "content-home")
            switcher.current = content_id

    def on_history_table_selected(self, event: HistoryTable.Selected) -> None:
        """User clicked a row in the history table — show the decision."""
        viewer = self.query_one("#decision-viewer", DecisionViewer)
        viewer.load_decision(event.run_id)
        self.query_one("#content-switcher", ContentSwitcher).current = "content-decision"

    def on_ask_form_debate_requested(self, event: AskForm.DebateRequested) -> None:
        """User pressed Start Debate — push the debate screen."""
        from .screens.debate import DebateScreen
        screen = DebateScreen(
            question=event.question,
            config_path=event.config_path,
            context_paths=event.context_paths,
            prior_id=event.prior_id,
            deep=event.deep,
        )
        self.push_screen(screen, callback=self._on_debate_done)

    def _on_debate_done(self, result: object) -> None:
        """Called when the debate screen is dismissed — refresh all data."""
        try:
            self.query_one("#sidebar", Sidebar).refresh_history()
        except Exception:
            pass
        try:
            self.query_one("#history-table", HistoryTable).load_runs()
        except Exception:
            pass

    def on_decision_viewer_continue_requested(self, event: DecisionViewer.ContinueRequested) -> None:
        """User wants to continue from a past decision — switch to Ask with prior pre-filled."""
        switcher = self.query_one("#content-switcher", ContentSwitcher)
        switcher.current = "content-ask"
        ask_form = self.query_one("#ask-form", AskForm)
        ask_form.set_prior(event.run_id)
        self.notify(f"Prior decision #{event.run_id} set as context. Type your follow-up question.", title="Continue")

    def action_switch(self, content_id: str) -> None:
        """Switch the content area to the given panel."""
        self.query_one("#content-switcher", ContentSwitcher).current = content_id
        # Refresh data when switching to history
        if content_id == "content-history":
            try:
                self.query_one("#history-table", HistoryTable).load_runs()
            except Exception:
                pass

    def on_config_builder_config_ready(self, event: ConfigBuilder.ConfigReady) -> None:
        """User finished building a config — save it."""
        from datetime import datetime
        from dissenter.paths import configs_dir, ensure_dirs

        ensure_dirs()
        name = event.output_name
        if not name:
            name = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"dissenter_{name}.toml"
        out_path = configs_dir() / filename

        # Build TOML
        lines = ['output_dir = "decisions"', ""]
        for rd in event.rounds_data:
            lines.append("[[rounds]]")
            lines.append(f'name = "{rd["name"]}"')
            lines.append("")
            for m in rd["models"]:
                lines.append("[[rounds.models]]")
                lines.append(f'id      = "{m["id"]}"')
                lines.append(f'role    = "{m["role"]}"')
                if m["auth"] != "api":
                    lines.append(f'auth    = "{m["auth"]}"')
                lines.append(f'timeout = {m.get("timeout", 180)}')
                if m["id"].startswith("ollama/"):
                    lines.append('extra   = { api_base = "http://localhost:11434" }')
                lines.append("")

        out_path.write_text("\n".join(lines), encoding="utf-8")
        self.notify(f"Saved: {out_path}", title="Config created")

    def action_toggle_help(self) -> None:
        """Toggle help overlay."""
        self.notify(
            "n Ask  g Generate  h History  q Quit  ? Help",
            title="Keybindings",
        )
