"""Benchmark run screen — live progress + final summary.

Worker thread drives dissenter.benchmark.run_benchmark and posts events
back to the TUI via call_from_thread. Mirrors the debate screen's
pattern (os._exit escape hatch + cancelled flag).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, RichLog, Static


class BenchmarkScreen(Screen):
    """Full-screen benchmark run with live per-question progress."""

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
    ]

    DEFAULT_CSS = """
    BenchmarkScreen {
        background: $surface;
    }
    BenchmarkScreen #bm-header {
        padding: 1 2;
        text-style: bold;
        color: $text;
        background: $primary-background;
    }
    BenchmarkScreen #bm-meta {
        padding: 0 2 1 2;
        color: $text-muted;
    }
    BenchmarkScreen #bm-log {
        margin: 1 2;
    }
    BenchmarkScreen #bm-summary {
        padding: 1 2;
        background: $panel;
        height: auto;
    }
    """

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
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._dataset_path = dataset_path
        self._config_path = config_path
        self._output_path = output_path
        self._limit = limit
        self._mode = mode
        self._majority_n = majority_n
        self._deep = deep
        self._competitor = competitor
        self._cancelled = False
        self._loop = None  # persistent asyncio loop for cancellation

    def compose(self) -> ComposeResult:
        yield Static("Benchmark running...", id="bm-header")
        yield Static(
            f"{Path(self._dataset_path).name} · {self._mode}"
            + (f" (competitor: {self._competitor})" if self._competitor else "")
            + (" + --deep" if self._deep else ""),
            id="bm-meta",
        )
        with VerticalScroll():
            yield RichLog(id="bm-log", markup=True, highlight=True)
            yield Static("", id="bm-summary")
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(
            self._benchmark_thread,
            thread=True,
            exclusive=True,
            name="benchmark-worker",
        )

    def _benchmark_thread(self) -> None:
        import asyncio

        from dissenter.config import load_config
        from dissenter.benchmark import run_benchmark
        from dissenter.benchmark.competitors import (
            LLMCouncil, LLMConsortium, Consilium,
        )

        loop = asyncio.new_event_loop()
        self._loop = loop

        try:
            cfg = load_config(Path(self._config_path) if self._config_path else None)

            comp = None
            if self._mode == "competitor":
                comp_map = {
                    "llm-council": LLMCouncil,
                    "llm-consortium": LLMConsortium,
                    "consilium": Consilium,
                }
                if self._competitor not in comp_map:
                    self._safe_log(f"[red]Unknown competitor: {self._competitor}[/red]")
                    return
                comp = comp_map[self._competitor]()
                try:
                    comp.validate()
                except Exception as e:
                    self._safe_log(f"[red]Competitor validation failed: {e}[/red]")
                    return

            self._safe_log(
                f"[bold]Starting benchmark[/bold] — dataset={Path(self._dataset_path).name} "
                f"mode={self._mode}" + (" --deep" if self._deep else "")
            )

            result = loop.run_until_complete(
                run_benchmark(
                    dataset_path=Path(self._dataset_path),
                    cfg=cfg,
                    output_path=Path(self._output_path),
                    limit=self._limit,
                    deep=self._deep,
                    mode=self._mode,
                    majority_n=self._majority_n,
                    competitor=comp,
                    progress=self._thread_progress,
                )
            )

            if not self._cancelled:
                self._safe_summary(result)

        except Exception as exc:
            if not self._cancelled:
                self._safe_log(f"[red]Error:[/red] {exc}")
        finally:
            loop.close()
            self._loop = None

    # ── thread → TUI bridges ───────────────────────────────────────────
    def _thread_progress(self, i: int, total: int, qr: Any) -> None:
        if qr.error:
            line = f"  [{i}/{total}] [yellow]![/yellow] {qr.id}: {qr.error[:60]}"
        elif qr.correct:
            line = f"  [{i}/{total}] [green]✓[/green] {qr.id}: pred={qr.predicted} truth={qr.ground_truth} [dim]({qr.latency_s:.1f}s)[/dim]"
        else:
            line = f"  [{i}/{total}] [red]✗[/red] {qr.id}: pred={qr.predicted} truth={qr.ground_truth} [dim]({qr.latency_s:.1f}s)[/dim]"
        self._safe_log(line)

    def _safe_log(self, text: str) -> None:
        try:
            app = self.app
        except Exception:
            return
        try:
            app.call_from_thread(self._append_log, text)
        except Exception:
            pass

    def _append_log(self, text: str) -> None:
        try:
            log = self.query_one("#bm-log", RichLog)
            log.write(text)
        except Exception:
            pass

    def _safe_summary(self, result) -> None:
        try:
            app = self.app
        except Exception:
            return
        try:
            app.call_from_thread(self._show_summary, result)
        except Exception:
            pass

    def _show_summary(self, result) -> None:
        try:
            header = self.query_one("#bm-header", Static)
            header.update("Benchmark complete")
            summary = self.query_one("#bm-summary", Static)
            avg = result.total_latency_s / max(1, result.total)
            summary.update(
                f"[bold]Accuracy:[/bold] {result.correct}/{result.total} "
                f"({result.accuracy * 100:.1f}%)\n"
                f"[bold]Errors:[/bold]   {result.errors}\n"
                f"[bold]Time:[/bold]     {result.total_latency_s:.1f}s ({avg:.1f}s/question)\n"
                f"[dim]Results: {self._output_path}[/dim]"
            )
        except Exception:
            pass

    def action_go_back(self) -> None:
        self._cancelled = True
        if self._loop and self._loop.is_running():
            import asyncio as _a
            for task in _a.all_tasks(self._loop):
                self._loop.call_soon_threadsafe(task.cancel)
        for worker in self.workers:
            worker.cancel()
        self.dismiss(True)
